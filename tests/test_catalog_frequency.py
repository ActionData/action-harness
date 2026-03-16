"""Tests for per-repo finding frequency tracking."""

import json
from pathlib import Path
from typing import Literal

from action_harness.catalog.frequency import (
    FREQUENCY_FILENAME,
    _finding_matches_entry,
    get_boosted_entries,
    update_frequency,
)
from action_harness.catalog.models import CatalogEntry
from action_harness.catalog.renderer import render_for_worker
from action_harness.models import ReviewFinding


def _make_entry(
    entry_id: str,
    rule: str = "Test rule",
    severity: Literal["high", "medium", "low"] = "medium",
) -> CatalogEntry:
    return CatalogEntry(
        id=entry_id,
        entry_class="test",
        severity=severity,
        ecosystems=["all"],
        worker_rule=rule,
        reviewer_checklist=["Check something"],
    )


def _make_finding(title: str, description: str = "") -> ReviewFinding:
    return ReviewFinding(
        title=title,
        file="src/test.py",
        severity="medium",
        description=description,
        agent="bug-hunter",
    )


class TestFindingMatchesEntry:
    def test_id_substring_match(self) -> None:
        entry = _make_entry("subprocess-timeout")
        finding = _make_finding("subprocess-timeout is missing")
        assert _finding_matches_entry(finding, entry) is True

    def test_id_case_insensitive(self) -> None:
        entry = _make_entry("subprocess-timeout")
        finding = _make_finding("SUBPROCESS-TIMEOUT issue found")
        assert _finding_matches_entry(finding, entry) is True

    def test_keyword_match(self) -> None:
        """The spec example: all non-stop-words from the rule appear in the finding."""
        entry = _make_entry(
            "subprocess-timeout",
            rule="Every subprocess.run() must include timeout=",
        )
        finding = _make_finding(
            "subprocess.run call missing timeout parameter",
        )
        assert _finding_matches_entry(finding, entry) is True

    def test_no_match(self) -> None:
        entry = _make_entry(
            "subprocess-timeout",
            rule="Every subprocess.run() must include timeout=",
        )
        finding = _make_finding("Missing docstring on public function")
        assert _finding_matches_entry(finding, entry) is False

    def test_keyword_match_with_backticks_in_rule(self) -> None:
        """Backtick-formatted code in worker_rule should not taint keywords."""
        entry = _make_entry(
            "bare-assert-narrowing",
            rule="Never use bare `assert x is not None` for type narrowing",
        )
        finding = _make_finding(
            "Uses assert for type narrowing",
            description="Found bare assert x is not None pattern",
        )
        assert _finding_matches_entry(finding, entry) is True

    def test_keyword_match_with_hash_in_rule(self) -> None:
        """Hash character in worker_rule should not taint keywords."""
        entry = _make_entry(
            "type-ignore-ban",
            rule="Never use `# type: ignore` comments",
        )
        finding = _make_finding(
            "type ignore comments found",
            description="Found # type: ignore suppressing a real error",
        )
        assert _finding_matches_entry(finding, entry) is True

    def test_id_match_in_description(self) -> None:
        entry = _make_entry("bare-assert-narrowing")
        finding = _make_finding(
            "Type narrowing issue",
            description="Uses bare-assert-narrowing pattern",
        )
        assert _finding_matches_entry(finding, entry) is True


class TestUpdateFrequency:
    def test_creates_file_on_first_match(self, tmp_path: Path) -> None:
        knowledge_dir = tmp_path / "knowledge"
        entry = _make_entry("subprocess-timeout")
        finding = _make_finding("subprocess-timeout is missing")

        update_frequency(knowledge_dir, [entry], [finding])

        freq_file = knowledge_dir / FREQUENCY_FILENAME
        assert freq_file.exists()
        data = json.loads(freq_file.read_text())
        assert data["subprocess-timeout"]["count"] == 1
        assert "last_seen" in data["subprocess-timeout"]

    def test_increments_on_subsequent_match(self, tmp_path: Path) -> None:
        knowledge_dir = tmp_path / "knowledge"
        entry = _make_entry("subprocess-timeout")
        finding = _make_finding("subprocess-timeout is missing")

        update_frequency(knowledge_dir, [entry], [finding])
        update_frequency(knowledge_dir, [entry], [finding])

        data = json.loads((knowledge_dir / FREQUENCY_FILENAME).read_text())
        assert data["subprocess-timeout"]["count"] == 2

    def test_no_match_no_file_created(self, tmp_path: Path) -> None:
        knowledge_dir = tmp_path / "knowledge"
        entry = _make_entry("subprocess-timeout", rule="subprocess.run timeout")
        finding = _make_finding("Missing docstring")

        update_frequency(knowledge_dir, [entry], [finding])

        assert not (knowledge_dir / FREQUENCY_FILENAME).exists()

    def test_multiple_findings_match_different_entries(self, tmp_path: Path) -> None:
        knowledge_dir = tmp_path / "knowledge"
        entry1 = _make_entry("subprocess-timeout")
        entry2 = _make_entry("bare-assert-narrowing")
        findings = [
            _make_finding("subprocess-timeout issue"),
            _make_finding("bare-assert-narrowing found"),
        ]

        update_frequency(knowledge_dir, [entry1, entry2], findings)

        data = json.loads((knowledge_dir / FREQUENCY_FILENAME).read_text())
        assert data["subprocess-timeout"]["count"] == 1
        assert data["bare-assert-narrowing"]["count"] == 1


class TestGetBoostedEntries:
    def test_returns_entries_above_threshold(self, tmp_path: Path) -> None:
        knowledge_dir = tmp_path / "knowledge"
        knowledge_dir.mkdir(parents=True)
        (knowledge_dir / FREQUENCY_FILENAME).write_text(
            json.dumps(
                {
                    "subprocess-timeout": {"count": 5, "last_seen": "2026-03-15"},
                    "bare-assert": {"count": 1, "last_seen": "2026-03-14"},
                }
            )
        )

        entry_hot = _make_entry("subprocess-timeout")
        entry_cold = _make_entry("bare-assert")
        entries = [entry_hot, entry_cold]

        boosted = get_boosted_entries(knowledge_dir, entries, threshold=3)
        assert len(boosted) == 1
        assert boosted[0].id == "subprocess-timeout"

    def test_returns_empty_when_no_frequency_file(self, tmp_path: Path) -> None:
        boosted = get_boosted_entries(tmp_path, [_make_entry("test")])
        assert boosted == []

    def test_sorted_by_frequency_descending(self, tmp_path: Path) -> None:
        knowledge_dir = tmp_path / "knowledge"
        knowledge_dir.mkdir(parents=True)
        (knowledge_dir / FREQUENCY_FILENAME).write_text(
            json.dumps(
                {
                    "entry-a": {"count": 3, "last_seen": "2026-03-15"},
                    "entry-b": {"count": 7, "last_seen": "2026-03-15"},
                }
            )
        )

        entries = [_make_entry("entry-a"), _make_entry("entry-b")]
        boosted = get_boosted_entries(knowledge_dir, entries, threshold=3)
        assert len(boosted) == 2
        assert boosted[0].id == "entry-b"
        assert boosted[1].id == "entry-a"


class TestRendererWithBoosted:
    def test_boosted_entries_included_in_output(self) -> None:
        base = [_make_entry("base", rule="Base rule")]
        boosted = [_make_entry("hot", rule="Hot rule")]
        result = render_for_worker(base, top_n=10, boosted=boosted)
        assert result is not None
        assert "Hot rule" in result
        assert "[repo-frequent]" in result
