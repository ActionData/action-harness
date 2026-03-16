"""Tests for catalog loader — ecosystem filtering, sort, and error handling."""

from pathlib import Path

from action_harness.catalog.loader import load_catalog


def _write_entry(entries_dir: Path, filename: str, content: str) -> None:
    """Helper to write a YAML entry file."""
    (entries_dir / filename).write_text(content)


def _make_python_entry(entries_dir: Path) -> None:
    _write_entry(
        entries_dir,
        "subprocess-timeout.yaml",
        """\
id: subprocess-timeout
class: defensive-io
severity: high
ecosystems: [python]
worker_rule: "Every subprocess.run() must include timeout="
reviewer_checklist:
  - "Check all subprocess.run calls have timeout="
""",
    )


def _make_all_entry(entries_dir: Path) -> None:
    _write_entry(
        entries_dir,
        "generic-error-messages.yaml",
        """\
id: generic-error-messages
class: error-clarity
severity: medium
ecosystems: [all]
worker_rule: "Include actual error text in error messages"
reviewer_checklist:
  - "Check error messages include original exception text"
""",
    )


def _make_js_entry(entries_dir: Path) -> None:
    _write_entry(
        entries_dir,
        "await-try-catch.yaml",
        """\
id: await-try-catch
class: language-pitfall
severity: high
ecosystems: [javascript]
worker_rule: "Every await must be in a try/catch"
reviewer_checklist:
  - "Check await calls have try/catch"
""",
    )


class TestLoadCatalogEcosystemFiltering:
    def test_python_returns_python_and_all_entries(self, tmp_path: Path) -> None:
        entries_dir = tmp_path / "entries"
        entries_dir.mkdir()
        _make_python_entry(entries_dir)
        _make_all_entry(entries_dir)
        _make_js_entry(entries_dir)

        result = load_catalog("python", entries_dir=entries_dir)
        ids = {e.id for e in result}
        assert "subprocess-timeout" in ids
        assert "generic-error-messages" in ids
        assert "await-try-catch" not in ids

    def test_unknown_returns_only_all_entries(self, tmp_path: Path) -> None:
        entries_dir = tmp_path / "entries"
        entries_dir.mkdir()
        _make_python_entry(entries_dir)
        _make_all_entry(entries_dir)

        result = load_catalog("unknown", entries_dir=entries_dir)
        ids = {e.id for e in result}
        assert "generic-error-messages" in ids
        assert "subprocess-timeout" not in ids

    def test_javascript_excludes_python_only(self, tmp_path: Path) -> None:
        entries_dir = tmp_path / "entries"
        entries_dir.mkdir()
        _make_python_entry(entries_dir)
        _make_all_entry(entries_dir)
        _make_js_entry(entries_dir)

        result = load_catalog("javascript", entries_dir=entries_dir)
        ids = {e.id for e in result}
        assert "await-try-catch" in ids
        assert "generic-error-messages" in ids
        assert "subprocess-timeout" not in ids

    def test_invalid_yaml_skipped_with_warning(self, tmp_path: Path) -> None:
        entries_dir = tmp_path / "entries"
        entries_dir.mkdir()
        _make_all_entry(entries_dir)
        _write_entry(entries_dir, "broken.yaml", ": invalid: yaml: [")

        result = load_catalog("python", entries_dir=entries_dir)
        assert len(result) == 1
        assert result[0].id == "generic-error-messages"

    def test_empty_entries_directory_returns_empty_list(self, tmp_path: Path) -> None:
        entries_dir = tmp_path / "entries"
        entries_dir.mkdir()

        result = load_catalog("python", entries_dir=entries_dir)
        assert result == []

    def test_nonexistent_entries_directory_returns_empty_list(self, tmp_path: Path) -> None:
        result = load_catalog("python", entries_dir=tmp_path / "does-not-exist")
        assert result == []


class TestLoadCatalogSorting:
    def test_sorted_by_severity_high_first(self, tmp_path: Path) -> None:
        entries_dir = tmp_path / "entries"
        entries_dir.mkdir()
        _write_entry(
            entries_dir,
            "low-entry.yaml",
            """\
id: low-sev
class: test
severity: low
ecosystems: [all]
worker_rule: "Low severity rule"
reviewer_checklist:
  - "Check low"
""",
        )
        _write_entry(
            entries_dir,
            "high-entry.yaml",
            """\
id: high-sev
class: test
severity: high
ecosystems: [all]
worker_rule: "High severity rule"
reviewer_checklist:
  - "Check high"
""",
        )
        _write_entry(
            entries_dir,
            "med-entry.yaml",
            """\
id: med-sev
class: test
severity: medium
ecosystems: [all]
worker_rule: "Medium severity rule"
reviewer_checklist:
  - "Check med"
""",
        )

        result = load_catalog("python", entries_dir=entries_dir)
        severities = [e.severity for e in result]
        assert severities == ["high", "medium", "low"]


class TestLoadCatalogClassRemap:
    def test_class_field_remapped_to_entry_class(self, tmp_path: Path) -> None:
        entries_dir = tmp_path / "entries"
        entries_dir.mkdir()
        _make_python_entry(entries_dir)

        result = load_catalog("python", entries_dir=entries_dir)
        assert result[0].entry_class == "defensive-io"

    def test_missing_required_field_skipped(self, tmp_path: Path) -> None:
        entries_dir = tmp_path / "entries"
        entries_dir.mkdir()
        _write_entry(
            entries_dir,
            "missing-fields.yaml",
            """\
id: incomplete
class: test
""",
        )
        _make_all_entry(entries_dir)

        result = load_catalog("python", entries_dir=entries_dir)
        assert len(result) == 1
        assert result[0].id == "generic-error-messages"
