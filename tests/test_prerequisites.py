"""Tests for the prerequisites module: parsing, satisfaction checks, and readiness computation."""

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from action_harness.cli import app
from action_harness.prerequisites import (
    compute_readiness,
    is_prerequisite_satisfied,
    read_prerequisites,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Task 1.2: read_prerequisites tests
# ---------------------------------------------------------------------------


class TestReadPrerequisites:
    def test_with_prerequisites(self, tmp_path: Path) -> None:
        """Change with prerequisites: [repo-lead, always-on] returns the list."""
        change_dir = tmp_path / "my-change"
        change_dir.mkdir()
        (change_dir / ".openspec.yaml").write_text(
            "schema: spec-driven\nprerequisites:\n  - repo-lead\n  - always-on\n"
        )

        result = read_prerequisites(change_dir)

        assert result == ["repo-lead", "always-on"]

    def test_no_prerequisites_field(self, tmp_path: Path) -> None:
        """No prerequisites field returns empty list."""
        change_dir = tmp_path / "my-change"
        change_dir.mkdir()
        (change_dir / ".openspec.yaml").write_text("schema: spec-driven\n")

        result = read_prerequisites(change_dir)

        assert result == []

    def test_missing_openspec_yaml(self, tmp_path: Path) -> None:
        """Missing .openspec.yaml returns empty list."""
        change_dir = tmp_path / "my-change"
        change_dir.mkdir()

        result = read_prerequisites(change_dir)

        assert result == []

    def test_malformed_yaml_returns_empty(self, tmp_path: Path, capfd: object) -> None:
        """Malformed YAML logs warning and returns empty list."""
        change_dir = tmp_path / "my-change"
        change_dir.mkdir()
        (change_dir / ".openspec.yaml").write_text(":\n  - [invalid yaml\n  }{")

        result = read_prerequisites(change_dir)

        assert result == []
        import _pytest.capture

        assert isinstance(capfd, _pytest.capture.CaptureFixture)
        captured = capfd.readouterr()
        assert "malformed YAML" in captured.err.lower() or "warning" in captured.err.lower()

    def test_prerequisites_not_a_list(self, tmp_path: Path) -> None:
        """Prerequisites field as a string (not list) returns empty list."""
        change_dir = tmp_path / "my-change"
        change_dir.mkdir()
        (change_dir / ".openspec.yaml").write_text(
            "schema: spec-driven\nprerequisites: repo-lead\n"
        )

        result = read_prerequisites(change_dir)

        assert result == []


# ---------------------------------------------------------------------------
# Task 2.2 / 2.3: is_prerequisite_satisfied and compute_readiness tests
# ---------------------------------------------------------------------------


class TestIsPrerequisiteSatisfied:
    def test_archived_prerequisite(self, tmp_path: Path) -> None:
        """Prerequisite satisfied when archived directory exists."""
        archive_dir = tmp_path / "openspec" / "changes" / "archive" / "2026-03-17-repo-lead"
        archive_dir.mkdir(parents=True)

        assert is_prerequisite_satisfied("repo-lead", tmp_path) is True

    def test_spec_exists(self, tmp_path: Path) -> None:
        """Prerequisite satisfied when spec directory exists."""
        spec_dir = tmp_path / "openspec" / "specs" / "repo-lead"
        spec_dir.mkdir(parents=True)

        assert is_prerequisite_satisfied("repo-lead", tmp_path) is True

    def test_not_satisfied(self, tmp_path: Path) -> None:
        """Prerequisite not satisfied when neither archived nor spec'd."""
        (tmp_path / "openspec" / "changes" / "archive").mkdir(parents=True)

        assert is_prerequisite_satisfied("repo-lead", tmp_path) is False

    def test_no_archive_dir(self, tmp_path: Path) -> None:
        """Returns False when archive directory doesn't exist."""
        assert is_prerequisite_satisfied("repo-lead", tmp_path) is False

    def test_suffix_collision_does_not_match(self, tmp_path: Path) -> None:
        """Archive dir '2026-03-17-repo-lead' must NOT satisfy prerequisite 'lead'."""
        archive_dir = tmp_path / "openspec" / "changes" / "archive" / "2026-03-17-repo-lead"
        archive_dir.mkdir(parents=True)

        assert is_prerequisite_satisfied("lead", tmp_path) is False


class TestComputeReadiness:
    def test_all_prerequisites_archived_is_ready(self, tmp_path: Path) -> None:
        """Change with all prerequisites archived is ready."""
        # Create archive for the prerequisite
        archive_dir = tmp_path / "openspec" / "changes" / "archive" / "2026-03-17-repo-lead"
        archive_dir.mkdir(parents=True)

        # Create active change with prerequisite
        change_dir = tmp_path / "openspec" / "changes" / "merge-queue"
        change_dir.mkdir(parents=True)
        (change_dir / ".openspec.yaml").write_text(
            "schema: spec-driven\nprerequisites:\n  - repo-lead\n"
        )

        ready, blocked = compute_readiness(tmp_path)

        assert "merge-queue" in ready
        assert all(b["name"] != "merge-queue" for b in blocked)

    def test_unmet_prerequisite_is_blocked(self, tmp_path: Path) -> None:
        """Change with unmet prerequisite is blocked."""
        (tmp_path / "openspec" / "changes" / "archive").mkdir(parents=True)

        # Create two active changes: always-on is a prereq for merge-queue
        always_on_dir = tmp_path / "openspec" / "changes" / "always-on"
        always_on_dir.mkdir(parents=True)
        (always_on_dir / ".openspec.yaml").write_text("schema: spec-driven\n")

        merge_queue_dir = tmp_path / "openspec" / "changes" / "merge-queue"
        merge_queue_dir.mkdir(parents=True)
        (merge_queue_dir / ".openspec.yaml").write_text(
            "schema: spec-driven\nprerequisites:\n  - always-on\n"
        )

        ready, blocked = compute_readiness(tmp_path)

        assert "always-on" in ready
        assert any(b["name"] == "merge-queue" for b in blocked)
        merge_queue_blocked = [b for b in blocked if b["name"] == "merge-queue"][0]
        assert "always-on" in merge_queue_blocked["unmet_prerequisites"]

    def test_no_prerequisites_is_ready(self, tmp_path: Path) -> None:
        """Change with no prerequisites is always ready."""
        change_dir = tmp_path / "openspec" / "changes" / "simple-change"
        change_dir.mkdir(parents=True)
        (change_dir / ".openspec.yaml").write_text("schema: spec-driven\n")

        ready, blocked = compute_readiness(tmp_path)

        assert "simple-change" in ready
        assert len(blocked) == 0

    def test_unknown_prerequisite_warns_and_unmet(self, tmp_path: Path, capfd: object) -> None:
        """Unknown prerequisite name logs warning and is treated as unmet."""
        change_dir = tmp_path / "openspec" / "changes" / "my-change"
        change_dir.mkdir(parents=True)
        (change_dir / ".openspec.yaml").write_text(
            "schema: spec-driven\nprerequisites:\n  - totally-unknown\n"
        )

        ready, blocked = compute_readiness(tmp_path)

        assert "my-change" not in ready
        assert any(b["name"] == "my-change" for b in blocked)

        import _pytest.capture

        assert isinstance(capfd, _pytest.capture.CaptureFixture)
        captured = capfd.readouterr()
        assert "unknown prerequisite" in captured.err.lower()
        assert "totally-unknown" in captured.err

    def test_active_prereq_sorted_after_is_known(self, tmp_path: Path, capfd: object) -> None:
        """Active change referenced as prerequisite is known regardless of sort order."""
        # 'a-feature' depends on 'z-feature'; both active. 'z-feature' sorts after
        # 'a-feature', so a naive single-pass would miss it in active_names.
        a_dir = tmp_path / "openspec" / "changes" / "a-feature"
        a_dir.mkdir(parents=True)
        (a_dir / ".openspec.yaml").write_text(
            "schema: spec-driven\nprerequisites:\n  - z-feature\n"
        )

        z_dir = tmp_path / "openspec" / "changes" / "z-feature"
        z_dir.mkdir(parents=True)
        (z_dir / ".openspec.yaml").write_text("schema: spec-driven\n")

        ready, blocked = compute_readiness(tmp_path)

        import _pytest.capture

        assert isinstance(capfd, _pytest.capture.CaptureFixture)
        captured = capfd.readouterr()
        # z-feature is active, so no "unknown prerequisite" warning should appear
        assert "unknown prerequisite" not in captured.err.lower()

    def test_no_active_changes(self, tmp_path: Path) -> None:
        """No active changes returns empty lists."""
        changes_dir = tmp_path / "openspec" / "changes"
        changes_dir.mkdir(parents=True)

        ready, blocked = compute_readiness(tmp_path)

        assert ready == []
        assert blocked == []

    def test_no_changes_dir(self, tmp_path: Path) -> None:
        """No openspec/changes/ directory returns empty lists."""
        ready, blocked = compute_readiness(tmp_path)

        assert ready == []
        assert blocked == []


# ---------------------------------------------------------------------------
# Task 3.3: CLI ready command tests
# ---------------------------------------------------------------------------


class TestReadyCLI:
    def test_help_shows_ready_command(self) -> None:
        """--help includes the ready command."""
        result = runner.invoke(app, ["ready", "--help"])
        assert result.exit_code == 0
        assert "ready" in result.output.lower()
        assert "--repo" in result.output

    def test_ready_changes_displayed(self, tmp_path: Path) -> None:
        """Command with ready changes displays them."""
        change_dir = tmp_path / "openspec" / "changes" / "my-change"
        change_dir.mkdir(parents=True)
        (change_dir / ".openspec.yaml").write_text("schema: spec-driven\n")

        result = runner.invoke(app, ["ready", "--repo", str(tmp_path)])

        assert result.exit_code == 0
        assert "my-change" in result.output

    def test_blocked_changes_show_unmet(self, tmp_path: Path) -> None:
        """Command with blocked changes shows unmet prerequisites."""
        change_dir = tmp_path / "openspec" / "changes" / "my-change"
        change_dir.mkdir(parents=True)
        (change_dir / ".openspec.yaml").write_text(
            "schema: spec-driven\nprerequisites:\n  - missing-dep\n"
        )

        result = runner.invoke(app, ["ready", "--repo", str(tmp_path)])

        assert result.exit_code == 0
        assert "my-change" in result.output
        assert "missing-dep" in result.output

    def test_json_output(self, tmp_path: Path) -> None:
        """--json produces valid JSON with correct keys."""
        change_dir = tmp_path / "openspec" / "changes" / "my-change"
        change_dir.mkdir(parents=True)
        (change_dir / ".openspec.yaml").write_text("schema: spec-driven\n")

        result = runner.invoke(app, ["ready", "--repo", str(tmp_path), "--json"])

        assert result.exit_code == 0
        # CliRunner mixes stderr into output; extract JSON object from the output
        output = result.output
        json_start = output.index("{")
        json_end = output.rindex("}") + 1
        data = json.loads(output[json_start:json_end])
        assert "ready" in data
        assert "blocked" in data
        assert "my-change" in data["ready"]

    def test_no_active_changes(self, tmp_path: Path) -> None:
        """No active changes outputs appropriate message."""
        changes_dir = tmp_path / "openspec" / "changes"
        changes_dir.mkdir(parents=True)

        result = runner.invoke(app, ["ready", "--repo", str(tmp_path)])

        assert result.exit_code == 0
        assert "No active changes found" in result.output


# ---------------------------------------------------------------------------
# Task 4.2: Lead integration test
# ---------------------------------------------------------------------------


class TestLeadIntegration:
    def test_gather_lead_context_includes_ready_changes(self, tmp_path: Path) -> None:
        """gather_lead_context with active changes includes Ready Changes section."""
        (tmp_path / ".git").mkdir()

        # Create an active change
        change_dir = tmp_path / "openspec" / "changes" / "my-feature"
        change_dir.mkdir(parents=True)
        (change_dir / ".openspec.yaml").write_text("schema: spec-driven\n")

        from action_harness.lead import gather_lead_context

        with patch("action_harness.lead._gather_issues", return_value=None):
            context = gather_lead_context(tmp_path)

        assert "Ready Changes" in context
        assert "my-feature" in context

    def test_gather_lead_context_no_ready_changes(self, tmp_path: Path) -> None:
        """gather_lead_context with no ready changes notes it."""
        (tmp_path / ".git").mkdir()

        # Create changes dir but no changes
        (tmp_path / "openspec" / "changes").mkdir(parents=True)

        from action_harness.lead import gather_lead_context

        with patch("action_harness.lead._gather_issues", return_value=None):
            context = gather_lead_context(tmp_path)

        assert "No changes currently ready for implementation" in context
