"""Tests for the seed catalog entries — verify all 10 load and have valid fields."""

from action_harness.catalog.loader import load_catalog


class TestSeedEntries:
    def test_all_10_entries_load_successfully(self) -> None:
        """Load all entries with ecosystem 'all' filter trick — use python + all."""
        # Load with 'python' to get python-specific + universal entries
        python_entries = load_catalog("python")
        # Load with 'unknown' to get only universal entries
        all_entries = load_catalog("unknown")

        # Combine unique IDs from both
        python_ids = {e.id for e in python_entries}
        all_ids = {e.id for e in all_entries}
        combined_ids = python_ids | all_ids

        expected_ids = {
            "subprocess-timeout",
            "bare-assert-narrowing",
            "type-ignore-ban",
            "regex-word-boundary",
            "generic-error-messages",
            "validate-before-operate",
            "inconsistent-error-handling",
            "duplicated-utility",
            "dry-run-mismatch",
            "string-field-access",
        }
        assert combined_ids == expected_ids

    def test_all_entries_have_valid_fields(self) -> None:
        python_entries = load_catalog("python")
        all_entries = load_catalog("unknown")
        entries = {e.id: e for e in python_entries + all_entries}

        for entry_id, entry in entries.items():
            assert entry.id, f"{entry_id} has empty id"
            assert entry.entry_class, f"{entry_id} has empty entry_class"
            assert entry.severity in ("high", "medium", "low"), (
                f"{entry_id} has invalid severity: {entry.severity}"
            )
            assert len(entry.ecosystems) > 0, f"{entry_id} has empty ecosystems"
            assert entry.worker_rule, f"{entry_id} has empty worker_rule"
            assert len(entry.reviewer_checklist) > 0, (
                f"{entry_id} has empty reviewer_checklist"
            )

    def test_at_least_6_tagged_python(self) -> None:
        python_entries = load_catalog("python")
        # Python entries include those with ecosystems: [python] AND [all]
        # We want to count only those specifically tagged with python
        python_specific = [e for e in python_entries if "python" in e.ecosystems]
        assert len(python_specific) >= 4  # subprocess-timeout, bare-assert, type-ignore, string-field

        # Total python-relevant (python + all) should be at least 6
        assert len(python_entries) >= 6

    def test_at_least_3_tagged_all(self) -> None:
        all_entries = load_catalog("unknown")
        assert len(all_entries) >= 3
        for entry in all_entries:
            assert "all" in entry.ecosystems
