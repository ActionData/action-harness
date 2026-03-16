"""Tests for catalog renderer — worker rules and reviewer checklists."""

from action_harness.catalog.models import CatalogEntry
from action_harness.catalog.renderer import render_for_reviewer, render_for_worker


def _make_entry(
    entry_id: str,
    severity: str = "medium",
    rule: str = "Test rule",
    checklist: list[str] | None = None,
    examples: dict[str, str] | None = None,
) -> CatalogEntry:
    return CatalogEntry(
        id=entry_id,
        entry_class="test",
        severity=severity,  # type: ignore[arg-type]
        ecosystems=["all"],
        worker_rule=rule,
        reviewer_checklist=checklist or ["Check something"],
        examples=examples,
    )


class TestRenderForWorker:
    def test_15_entries_top_n_10_returns_10_rules(self) -> None:
        entries = [_make_entry(f"entry-{i}", rule=f"Rule {i}") for i in range(15)]
        result = render_for_worker(entries, top_n=10)
        assert result is not None
        # Count bullet lines (lines starting with "- ")
        rule_lines = [ln for ln in result.split("\n") if ln.startswith("- ")]
        assert len(rule_lines) == 10

    def test_3_entries_returns_3_rules(self) -> None:
        entries = [_make_entry(f"entry-{i}", rule=f"Rule {i}") for i in range(3)]
        result = render_for_worker(entries, top_n=10)
        assert result is not None
        rule_lines = [ln for ln in result.split("\n") if ln.startswith("- ")]
        assert len(rule_lines) == 3

    def test_0_entries_returns_none(self) -> None:
        result = render_for_worker([], top_n=10)
        assert result is None

    def test_contains_quality_rules_header(self) -> None:
        entries = [_make_entry("test")]
        result = render_for_worker(entries)
        assert result is not None
        assert "## Quality Rules" in result

    def test_sorted_by_severity(self) -> None:
        entries = [
            _make_entry("low", severity="low", rule="Low rule"),
            _make_entry("high", severity="high", rule="High rule"),
            _make_entry("med", severity="medium", rule="Medium rule"),
        ]
        result = render_for_worker(entries, top_n=10)
        assert result is not None
        lines = result.split("\n")
        rule_lines = [ln for ln in lines if ln.startswith("- ")]
        assert "High rule" in rule_lines[0]
        assert "Medium rule" in rule_lines[1]
        assert "Low rule" in rule_lines[2]

    def test_boosted_entries_appended(self) -> None:
        entries = [_make_entry("base", rule="Base rule")]
        boosted = [_make_entry("hot", rule="Hot rule")]
        result = render_for_worker(entries, top_n=10, boosted=boosted)
        assert result is not None
        assert "[repo-frequent] Hot rule" in result

    def test_boosted_max_2_extra(self) -> None:
        entries = [_make_entry("base", rule="Base rule")]
        boosted = [
            _make_entry("hot1", rule="Hot 1"),
            _make_entry("hot2", rule="Hot 2"),
            _make_entry("hot3", rule="Hot 3"),
        ]
        result = render_for_worker(entries, top_n=10, boosted=boosted)
        assert result is not None
        rule_lines = [ln for ln in result.split("\n") if ln.startswith("- ")]
        # 1 base + 2 boosted (3rd excluded)
        assert len(rule_lines) == 3
        assert "Hot 3" not in result

    def test_boosted_deduplicates_against_selected(self) -> None:
        entry = _make_entry("shared", rule="Shared rule")
        result = render_for_worker([entry], top_n=10, boosted=[entry])
        assert result is not None
        rule_lines = [ln for ln in result.split("\n") if ln.startswith("- ")]
        # Should not duplicate
        assert len(rule_lines) == 1


class TestRenderForReviewer:
    def test_includes_checklist_items(self) -> None:
        entries = [
            _make_entry(
                "test-entry",
                checklist=["Check A", "Check B"],
            )
        ]
        result = render_for_reviewer(entries)
        assert result is not None
        assert "Check A" in result
        assert "Check B" in result

    def test_includes_examples(self) -> None:
        entries = [
            _make_entry(
                "test-entry",
                examples={"bad": "bad_code()", "good": "good_code()"},
            )
        ]
        result = render_for_reviewer(entries)
        assert result is not None
        assert "bad_code()" in result
        assert "good_code()" in result

    def test_includes_entry_id_and_severity(self) -> None:
        entries = [_make_entry("my-rule", severity="high")]
        result = render_for_reviewer(entries)
        assert result is not None
        assert "my-rule" in result
        assert "high" in result

    def test_0_entries_returns_none(self) -> None:
        result = render_for_reviewer([])
        assert result is None

    def test_contains_catalog_checklist_header(self) -> None:
        entries = [_make_entry("test")]
        result = render_for_reviewer(entries)
        assert result is not None
        assert "## Catalog Checklist" in result

    def test_all_entries_present(self) -> None:
        entries = [_make_entry(f"entry-{i}") for i in range(10)]
        result = render_for_reviewer(entries)
        assert result is not None
        for i in range(10):
            assert f"entry-{i}" in result
