"""Tests for the repo lead module: agent file, context gathering, dispatch, plan parsing, CLI."""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from action_harness.agents import parse_agent_file
from action_harness.cli import app
from action_harness.lead import (
    DispatchItem,
    IssueItem,
    LeadContext,
    LeadPlan,
    ProposalItem,
    _build_active_names,
    _compute_readiness_safe,
    _gather_issues,
    _gather_recent_runs,
    build_greeting,
    dispatch_lead,
    dispatch_lead_interactive,
    gather_lead_context,
    parse_lead_plan,
)
from action_harness.models import EvalResult, RunManifest, WorkerResult, WorktreeResult

runner = CliRunner()


def _mock_gather_issues_none(*_args: object, **_kwargs: object) -> None:
    """Replacement for _gather_issues that returns None (no gh available)."""
    return None


# ---------------------------------------------------------------------------
# Task 1.2: Lead agent file tests
# ---------------------------------------------------------------------------


class TestLeadAgentFile:
    def test_lead_agent_file_exists(self) -> None:
        """Lead agent definition file exists at .harness/agents/lead.md."""
        agents_dir = Path(__file__).resolve().parent.parent / ".harness" / "agents"
        lead_path = agents_dir / "lead.md"
        assert lead_path.exists(), "Missing .harness/agents/lead.md"

    def test_lead_agent_has_valid_frontmatter(self) -> None:
        """Lead agent file has valid YAML frontmatter with name and description."""
        agents_dir = Path(__file__).resolve().parent.parent / ".harness" / "agents"
        lead_path = agents_dir / "lead.md"
        meta, body = parse_agent_file(lead_path)

        assert meta.get("name") == "lead"
        assert "description" in meta
        assert len(meta["description"]) > 0

    def test_lead_agent_body_contains_capabilities(self) -> None:
        """Lead agent body describes key capabilities."""
        agents_dir = Path(__file__).resolve().parent.parent / ".harness" / "agents"
        lead_path = agents_dir / "lead.md"
        _, body = parse_agent_file(lead_path)

        assert "technical lead" in body.lower()
        assert "proposals" in body.lower()
        assert "issues" in body.lower()
        assert "dispatches" in body.lower()
        assert "prioriti" in body.lower()  # "prioritize" or "prioritization"


# ---------------------------------------------------------------------------
# Task 2.2: Context gathering tests
# ---------------------------------------------------------------------------


class TestGatherLeadContext:
    def test_includes_roadmap_and_claude_md(self, tmp_path: Path) -> None:
        """Context includes ROADMAP.md and CLAUDE.md when both exist."""
        (tmp_path / "ROADMAP.md").write_text("# Roadmap\n\n1. First change")
        (tmp_path / "CLAUDE.md").write_text("# Project\n\nBuild instructions")
        # Create .git so it looks like a repo
        (tmp_path / ".git").mkdir()

        with patch("action_harness.lead._gather_issues", return_value=None):
            lead_ctx = gather_lead_context(tmp_path)

        assert "Roadmap" in lead_ctx.full_text
        assert "First change" in lead_ctx.full_text
        assert "CLAUDE.md" in lead_ctx.full_text
        assert "Build instructions" in lead_ctx.full_text

    def test_missing_files_skipped(self, tmp_path: Path) -> None:
        """Missing context files are skipped without error."""
        (tmp_path / ".git").mkdir()

        with patch("action_harness.lead._gather_issues", return_value=None):
            lead_ctx = gather_lead_context(tmp_path)

        # Should return minimal context, not crash
        assert "context" in lead_ctx.full_text.lower() or "Repo Context" in lead_ctx.full_text

    def test_gh_failure_is_nonfatal(self, tmp_path: Path) -> None:
        """gh failure is non-fatal — warning logged, issues section omitted."""
        (tmp_path / ".git").mkdir()
        (tmp_path / "CLAUDE.md").write_text("# Test project")

        # Simulate gh not being available
        with patch(
            "action_harness.lead.subprocess.run",
            side_effect=FileNotFoundError("gh not found"),
        ):
            lead_ctx = gather_lead_context(tmp_path)

        # Should still have CLAUDE.md content
        assert "Test project" in lead_ctx.full_text
        # Should NOT have issues section
        assert "Open Issues" not in lead_ctx.full_text

    def test_empty_repo_returns_minimal_context(self, tmp_path: Path) -> None:
        """Empty repo returns minimal context with a note."""
        (tmp_path / ".git").mkdir()

        with patch("action_harness.lead._gather_issues", return_value=None):
            lead_ctx = gather_lead_context(tmp_path)

        text = lead_ctx.full_text
        assert "No context files found" in text or "Repo Context" in text

    def test_openspec_roadmap_preferred(self, tmp_path: Path) -> None:
        """openspec/ROADMAP.md is preferred over root ROADMAP.md."""
        (tmp_path / ".git").mkdir()
        (tmp_path / "ROADMAP.md").write_text("Root roadmap")
        openspec = tmp_path / "openspec"
        openspec.mkdir()
        (openspec / "ROADMAP.md").write_text("OpenSpec roadmap content")

        with patch("action_harness.lead._gather_issues", return_value=None):
            lead_ctx = gather_lead_context(tmp_path)

        assert "OpenSpec roadmap content" in lead_ctx.full_text

    def test_harness_md_included(self, tmp_path: Path) -> None:
        """HARNESS.md is included in context when present."""
        (tmp_path / ".git").mkdir()
        (tmp_path / "HARNESS.md").write_text("Run pytest to validate")

        with patch("action_harness.lead._gather_issues", return_value=None):
            lead_ctx = gather_lead_context(tmp_path)

        assert "HARNESS.md" in lead_ctx.full_text
        assert "pytest" in lead_ctx.full_text


# ---------------------------------------------------------------------------
# Task 3.2: Dispatch tests
# ---------------------------------------------------------------------------


class TestDispatchLead:
    def test_dispatch_returns_output(self, tmp_path: Path) -> None:
        """Dispatch with mock subprocess returns the CLI output."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "lead.md").write_text("---\nname: lead\n---\nYou are a lead.")

        mock_output = json.dumps({"result": '{"summary": "test plan"}'})
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=mock_output, stderr=""
        )

        with patch("action_harness.lead.subprocess.run", return_value=mock_result):
            output = dispatch_lead(
                repo_path=repo_path,
                prompt="What should we do?",
                context="# Context\n\nSome context",
                harness_agents_dir=agents_dir,
            )

        assert "test plan" in output

    def test_dispatch_uses_persona_from_file(self, tmp_path: Path) -> None:
        """Dispatch loads persona from the agent file."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "lead.md").write_text("---\nname: lead\n---\nCustom persona text")

        mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="{}", stderr="")

        with patch("action_harness.lead.subprocess.run", return_value=mock_result) as mock_run:
            dispatch_lead(
                repo_path=repo_path,
                prompt="test",
                context="ctx",
                harness_agents_dir=agents_dir,
            )

        # Verify the system prompt contains the persona
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        system_prompt_idx = cmd.index("--system-prompt")
        system_prompt = cmd[system_prompt_idx + 1]
        assert "Custom persona text" in system_prompt

    def test_dispatch_timeout_returns_error(self, tmp_path: Path) -> None:
        """Timeout returns error JSON, doesn't crash."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "lead.md").write_text("---\nname: lead\n---\nPersona")

        with patch(
            "action_harness.lead.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=7200),
        ):
            output = dispatch_lead(
                repo_path=repo_path,
                prompt="test",
                context="ctx",
                harness_agents_dir=agents_dir,
            )

        data = json.loads(output)
        assert "error" in data
        assert "timed out" in data["error"].lower()

    def test_dispatch_file_not_found_returns_error(self, tmp_path: Path) -> None:
        """FileNotFoundError returns error JSON, doesn't crash."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "lead.md").write_text("---\nname: lead\n---\nPersona")

        with patch(
            "action_harness.lead.subprocess.run",
            side_effect=FileNotFoundError("claude not found"),
        ):
            output = dispatch_lead(
                repo_path=repo_path,
                prompt="test",
                context="ctx",
                harness_agents_dir=agents_dir,
            )

        data = json.loads(output)
        assert "error" in data
        assert "claude" in data["error"].lower()

    def test_dispatch_permission_mode(self, tmp_path: Path) -> None:
        """Dispatch uses default permission mode."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "lead.md").write_text("---\nname: lead\n---\nPersona")

        mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="{}", stderr="")

        with patch("action_harness.lead.subprocess.run", return_value=mock_result) as mock_run:
            dispatch_lead(
                repo_path=repo_path,
                prompt="test",
                context="ctx",
                harness_agents_dir=agents_dir,
            )

        cmd = mock_run.call_args[0][0]
        pm_idx = cmd.index("--permission-mode")
        assert cmd[pm_idx + 1] == "default"


# ---------------------------------------------------------------------------
# dispatch_lead_interactive tests
# ---------------------------------------------------------------------------


class TestDispatchLeadInteractive:
    def test_command_has_no_dash_p(self, tmp_path: Path) -> None:
        """Interactive dispatch uses `claude` without `-p`."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "lead.md").write_text("---\nname: lead\n---\nYou are a lead.")

        mock_result = subprocess.CompletedProcess(args=[], returncode=0)

        with patch("action_harness.lead.subprocess.run", return_value=mock_result) as mock_run:
            exit_code = dispatch_lead_interactive(
                repo_path=repo_path,
                prompt="What next?",
                context=LeadContext(full_text="# Context\n\nRepo context here", repo_name="repo"),
                harness_agents_dir=agents_dir,
            )

        assert exit_code == 0
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "claude"
        assert "-p" not in cmd

    def test_command_uses_system_prompt_and_append(self, tmp_path: Path) -> None:
        """Interactive dispatch uses --system-prompt and --append-system-prompt."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "lead.md").write_text("---\nname: lead\n---\nCustom persona")

        mock_result = subprocess.CompletedProcess(args=[], returncode=0)

        with patch("action_harness.lead.subprocess.run", return_value=mock_result) as mock_run:
            dispatch_lead_interactive(
                repo_path=repo_path,
                prompt="Focus on tests",
                context=LeadContext(full_text="# Repo Context\n\nTest info", repo_name="repo"),
                harness_agents_dir=agents_dir,
            )

        cmd = mock_run.call_args[0][0]

        # --system-prompt has the persona
        sp_idx = cmd.index("--system-prompt")
        assert "Custom persona" in cmd[sp_idx + 1]

        # --append-system-prompt has the context
        asp_idx = cmd.index("--append-system-prompt")
        assert "Repo Context" in cmd[asp_idx + 1]

    def test_prompt_passed_as_positional(self, tmp_path: Path) -> None:
        """User prompt is passed as a positional argument (second element after 'claude')."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "lead.md").write_text("---\nname: lead\n---\nPersona")

        mock_result = subprocess.CompletedProcess(args=[], returncode=0)
        ctx = LeadContext(full_text="ctx", repo_name="repo")

        with patch("action_harness.lead.subprocess.run", return_value=mock_result) as mock_run:
            dispatch_lead_interactive(
                repo_path=repo_path,
                prompt="My specific question",
                context=ctx,
                harness_agents_dir=agents_dir,
            )

        cmd = mock_run.call_args[0][0]
        assert cmd[1] == "My specific question"

    def test_no_capture_output(self, tmp_path: Path) -> None:
        """Interactive dispatch does NOT use capture_output (inherited stdio)."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "lead.md").write_text("---\nname: lead\n---\nPersona")

        mock_result = subprocess.CompletedProcess(args=[], returncode=0)
        ctx = LeadContext(full_text="ctx", repo_name="repo")

        with patch("action_harness.lead.subprocess.run", return_value=mock_result) as mock_run:
            dispatch_lead_interactive(
                repo_path=repo_path,
                prompt="test",
                context=ctx,
                harness_agents_dir=agents_dir,
            )

        kwargs = mock_run.call_args[1]
        assert "capture_output" not in kwargs or kwargs["capture_output"] is False

    def test_returns_exit_code(self, tmp_path: Path) -> None:
        """Returns the subprocess exit code."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "lead.md").write_text("---\nname: lead\n---\nPersona")

        mock_result = subprocess.CompletedProcess(args=[], returncode=42)
        ctx = LeadContext(full_text="ctx", repo_name="repo")

        with patch("action_harness.lead.subprocess.run", return_value=mock_result):
            exit_code = dispatch_lead_interactive(
                repo_path=repo_path,
                prompt="test",
                context=ctx,
                harness_agents_dir=agents_dir,
            )

        assert exit_code == 42

    def test_timeout_returns_error_code(self, tmp_path: Path) -> None:
        """Timeout returns exit code 1."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "lead.md").write_text("---\nname: lead\n---\nPersona")
        ctx = LeadContext(full_text="ctx", repo_name="repo")

        with patch(
            "action_harness.lead.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=7200),
        ):
            exit_code = dispatch_lead_interactive(
                repo_path=repo_path,
                prompt="test",
                context=ctx,
                harness_agents_dir=agents_dir,
            )

        assert exit_code == 1

    def test_file_not_found_returns_error_code(self, tmp_path: Path) -> None:
        """FileNotFoundError returns exit code 1."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "lead.md").write_text("---\nname: lead\n---\nPersona")
        ctx = LeadContext(full_text="ctx", repo_name="repo")

        with patch(
            "action_harness.lead.subprocess.run",
            side_effect=FileNotFoundError("claude not found"),
        ):
            exit_code = dispatch_lead_interactive(
                repo_path=repo_path,
                prompt="test",
                context=ctx,
                harness_agents_dir=agents_dir,
            )

        assert exit_code == 1

    def test_missing_agent_file_returns_error_code(self, tmp_path: Path) -> None:
        """Missing lead.md returns exit code 1."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        # No lead.md
        ctx = LeadContext(full_text="ctx", repo_name="repo")

        exit_code = dispatch_lead_interactive(
            repo_path=repo_path,
            prompt="test",
            context=ctx,
            harness_agents_dir=agents_dir,
        )

        assert exit_code == 1

    def test_none_prompt_uses_built_greeting(self, tmp_path: Path) -> None:
        """None prompt passes a built greeting as the positional argument."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "lead.md").write_text("---\nname: lead\n---\nPersona")
        ctx = LeadContext(
            full_text="ctx",
            repo_name="my-repo",
            active_changes=["feature-a"],
            ready_changes=["feature-a"],
        )

        with patch("action_harness.lead.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            dispatch_lead_interactive(
                repo_path=repo_path,
                prompt=None,
                context=ctx,
                harness_agents_dir=agents_dir,
            )

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        # Greeting IS passed as positional arg (no longer omitted)
        assert cmd[0] == "claude"
        assert cmd[1] != "--system-prompt"  # positional arg comes before flags
        assert "my-repo" in cmd[1]
        assert "feature-a" in cmd[1]


# ---------------------------------------------------------------------------
# Greeting builder tests
# ---------------------------------------------------------------------------


class TestBuildGreeting:
    def test_full_context_produces_complete_greeting(self) -> None:
        """build_greeting includes all populated fields."""
        ctx = LeadContext(
            full_text="...",
            repo_name="action-harness",
            active_changes=["feature-a", "feature-b"],
            ready_changes=["feature-a"],
            recent_run_stats=(4, 5),
        )
        greeting = build_greeting(ctx)

        assert "action-harness" in greeting
        assert "feature-a" in greeting
        assert "feature-b" in greeting
        assert "Ready to implement: feature-a" in greeting
        assert "4/5 passed" in greeting
        assert "Greet me" in greeting

    def test_empty_context_produces_minimal_greeting(self) -> None:
        """build_greeting with empty fields produces minimal greeting."""
        ctx = LeadContext(full_text="...", repo_name="my-repo")
        greeting = build_greeting(ctx)

        assert "my-repo" in greeting
        assert "Greet me" in greeting
        # Should NOT contain optional sections
        assert "Active changes" not in greeting
        assert "Ready to implement" not in greeting
        assert "Recent runs" not in greeting

    def test_no_run_stats_omits_runs_line(self) -> None:
        """build_greeting with no run stats omits the runs line."""
        ctx = LeadContext(
            full_text="...",
            repo_name="test-repo",
            active_changes=["change-1"],
            recent_run_stats=None,
        )
        greeting = build_greeting(ctx)

        assert "Recent runs" not in greeting
        assert "change-1" in greeting


class TestGatherLeadContextStructured:
    def test_returns_lead_context_with_repo_name(self, tmp_path: Path) -> None:
        """gather_lead_context returns LeadContext with repo_name set."""
        (tmp_path / ".git").mkdir()
        (tmp_path / "CLAUDE.md").write_text("# Project")

        with patch("action_harness.lead._gather_issues", return_value=None):
            lead_ctx = gather_lead_context(tmp_path)

        assert isinstance(lead_ctx, LeadContext)
        assert lead_ctx.repo_name == tmp_path.name
        assert lead_ctx.full_text  # non-empty

    def test_has_roadmap_flag_set(self, tmp_path: Path) -> None:
        """has_roadmap is True when ROADMAP.md exists."""
        (tmp_path / ".git").mkdir()
        (tmp_path / "ROADMAP.md").write_text("# Roadmap")

        with patch("action_harness.lead._gather_issues", return_value=None):
            lead_ctx = gather_lead_context(tmp_path)

        assert lead_ctx.has_roadmap is True

    def test_has_claude_md_flag_set(self, tmp_path: Path) -> None:
        """has_claude_md is True when CLAUDE.md exists."""
        (tmp_path / ".git").mkdir()
        (tmp_path / "CLAUDE.md").write_text("# Claude")

        with patch("action_harness.lead._gather_issues", return_value=None):
            lead_ctx = gather_lead_context(tmp_path)

        assert lead_ctx.has_claude_md is True

    def test_flags_false_when_files_missing(self, tmp_path: Path) -> None:
        """has_roadmap and has_claude_md are False when files don't exist."""
        (tmp_path / ".git").mkdir()

        with patch("action_harness.lead._gather_issues", return_value=None):
            lead_ctx = gather_lead_context(tmp_path)

        assert lead_ctx.has_roadmap is False
        assert lead_ctx.has_claude_md is False

    def test_active_and_ready_changes_populated(self, tmp_path: Path) -> None:
        """active_changes and ready_changes populated from prerequisites."""
        (tmp_path / ".git").mkdir()
        (tmp_path / "CLAUDE.md").write_text("# Project")
        change_dir = tmp_path / "openspec" / "changes" / "my-feature"
        change_dir.mkdir(parents=True)
        (change_dir / ".openspec.yaml").write_text("schema: spec-driven\n")

        with patch("action_harness.lead._gather_issues", return_value=None):
            lead_ctx = gather_lead_context(tmp_path)

        assert "my-feature" in lead_ctx.ready_changes
        assert "my-feature" in lead_ctx.active_changes

    def test_recent_run_stats_populated_from_manifests(self, tmp_path: Path) -> None:
        """recent_run_stats populated when manifests exist."""
        (tmp_path / ".git").mkdir()
        (tmp_path / "CLAUDE.md").write_text("# Project")

        mock_manifest = type(
            "M", (), {"success": True, "change_name": "x", "total_duration_seconds": 10.0}
        )()
        mock_fail = type(
            "M", (), {"success": False, "change_name": "y", "total_duration_seconds": 5.0}
        )()

        with (
            patch("action_harness.lead._gather_issues", return_value=None),
            patch(
                "action_harness.reporting.load_manifests",
                return_value=[mock_manifest, mock_fail, mock_manifest],
            ),
        ):
            lead_ctx = gather_lead_context(tmp_path)

        assert lead_ctx.recent_run_stats == (2, 3)


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestBuildActiveNames:
    def test_ready_only(self) -> None:
        """Returns ready names when no blocked changes."""
        result = _build_active_names(["a", "b"], [])
        assert result == ["a", "b"]

    def test_ready_plus_blocked(self) -> None:
        """Combines ready and blocked names."""
        blocked = [{"name": "c", "unmet": ["dep"]}]
        result = _build_active_names(["a"], blocked)
        assert result == ["a", "c"]

    def test_malformed_blocked_entries_skipped(self) -> None:
        """Non-dict and missing-name entries are skipped."""
        blocked: list[dict[str, str | list[str]]] = [
            {"name": "valid"},
            {"no_name_key": "bad"},
        ]
        result = _build_active_names([], blocked)
        assert result == ["valid"]

    def test_empty_inputs(self) -> None:
        """Both empty returns empty."""
        result = _build_active_names([], [])
        assert result == []


class TestComputeReadinessSafe:
    def test_exception_returns_empty(self, tmp_path: Path) -> None:
        """Exception from compute_readiness returns empty lists."""
        with patch(
            "action_harness.prerequisites.compute_readiness",
            side_effect=RuntimeError("boom"),
        ):
            ready, blocked = _compute_readiness_safe(tmp_path)

        assert ready == []
        assert blocked == []


class TestGatherRecentRuns:
    def test_returns_section_and_stats(self, tmp_path: Path) -> None:
        """Returns both section text and structured stats."""
        manifest_pass = RunManifest(
            change_name="feat",
            repo_path=str(tmp_path),
            started_at="2026-03-16T10:00:00+00:00",
            completed_at="2026-03-16T10:00:10+00:00",
            success=True,
            stages=[
                WorktreeResult(success=True, worktree_path=tmp_path),
                WorkerResult(success=True),
                EvalResult(success=True, commands_run=1, commands_passed=1),
            ],
            total_duration_seconds=10.0,
        )
        manifest_fail = RunManifest(
            change_name="fix",
            repo_path=str(tmp_path),
            started_at="2026-03-16T10:01:00+00:00",
            completed_at="2026-03-16T10:01:05+00:00",
            success=False,
            stages=[
                WorktreeResult(success=True, worktree_path=tmp_path),
                WorkerResult(success=True),
                EvalResult(success=False, commands_run=1, commands_passed=0),
            ],
            total_duration_seconds=5.0,
        )

        with patch(
            "action_harness.reporting.load_manifests",
            return_value=[manifest_pass, manifest_fail],
        ):
            section, stats = _gather_recent_runs(tmp_path, 3000)

        assert section is not None
        assert "feat" in section
        assert "fix" in section
        assert stats == (1, 2)

    def test_no_manifests_returns_none(self, tmp_path: Path) -> None:
        """No manifests returns (None, None)."""
        with patch("action_harness.reporting.load_manifests", return_value=[]):
            section, stats = _gather_recent_runs(tmp_path, 3000)

        assert section is None
        assert stats is None

    def test_load_error_returns_none(self, tmp_path: Path) -> None:
        """Exception from load_manifests returns (None, None)."""
        with patch(
            "action_harness.reporting.load_manifests",
            side_effect=OSError("corrupt"),
        ):
            section, stats = _gather_recent_runs(tmp_path, 3000)

        assert section is None
        assert stats is None


class TestEmptyPromptUsesGreeting:
    def test_empty_string_prompt_triggers_greeting(self, tmp_path: Path) -> None:
        """Empty-string prompt is treated as no-prompt — greeting is injected."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "lead.md").write_text("---\nname: lead\n---\nPersona")
        ctx = LeadContext(full_text="ctx", repo_name="my-repo", active_changes=["feat"])

        with patch("action_harness.lead.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            dispatch_lead_interactive(
                repo_path=repo_path,
                prompt="",
                context=ctx,
                harness_agents_dir=agents_dir,
            )

        cmd = mock_run.call_args[0][0]
        # Empty-string prompt triggers greeting, not passed as-is
        assert "my-repo" in cmd[1]
        assert "Greet me" in cmd[1]

    def test_whitespace_only_prompt_triggers_greeting(self, tmp_path: Path) -> None:
        """Whitespace-only prompt is treated as no-prompt — greeting is injected."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "lead.md").write_text("---\nname: lead\n---\nPersona")
        ctx = LeadContext(full_text="ctx", repo_name="my-repo")

        with patch("action_harness.lead.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            dispatch_lead_interactive(
                repo_path=repo_path,
                prompt="   ",
                context=ctx,
                harness_agents_dir=agents_dir,
            )

        cmd = mock_run.call_args[0][0]
        assert "my-repo" in cmd[1]


# ---------------------------------------------------------------------------
# Task 4.2: Plan parsing tests
# ---------------------------------------------------------------------------


class TestParseLeadPlan:
    def test_parse_valid_plan(self) -> None:
        """Valid plan JSON returns populated LeadPlan."""
        plan_data = {
            "summary": "The repo needs work",
            "proposals": [
                {"name": "add-auth", "description": "Add authentication", "priority": "high"}
            ],
            "issues": [{"title": "Fix login", "body": "Login is broken", "labels": ["bug"]}],
            "dispatches": [{"change": "add-logging"}],
        }
        raw = json.dumps({"result": json.dumps(plan_data)})

        plan = parse_lead_plan(raw)

        assert plan.summary == "The repo needs work"
        assert len(plan.proposals) == 1
        assert plan.proposals[0].name == "add-auth"
        assert plan.proposals[0].priority == "high"
        assert len(plan.issues) == 1
        assert plan.issues[0].title == "Fix login"
        assert plan.issues[0].labels == ["bug"]
        assert len(plan.dispatches) == 1
        assert plan.dispatches[0].change == "add-logging"

    def test_parse_malformed_output_returns_empty(self) -> None:
        """Malformed output returns empty LeadPlan with warning."""
        plan = parse_lead_plan("not json at all {{{")

        assert isinstance(plan, LeadPlan)
        assert plan.summary == ""
        assert plan.proposals == []
        assert plan.issues == []
        assert plan.dispatches == []

    def test_parse_no_json_block_returns_empty_with_raw_text(self) -> None:
        """Output with no JSON block returns LeadPlan with summary from raw text."""
        raw = json.dumps({"result": "Here is my analysis without any JSON"})

        plan = parse_lead_plan(raw)

        assert isinstance(plan, LeadPlan)
        # summary gets set to the raw text since no JSON block found
        assert "analysis" in plan.summary.lower()

    def test_parse_empty_result_returns_empty(self) -> None:
        """Empty result field returns empty LeadPlan."""
        raw = json.dumps({"result": ""})

        plan = parse_lead_plan(raw)

        assert isinstance(plan, LeadPlan)
        assert plan.summary == ""

    def test_model_roundtrip(self) -> None:
        """LeadPlan roundtrips through model_dump_json / model_validate_json."""
        plan = LeadPlan(
            summary="Test",
            proposals=[ProposalItem(name="x", description="y", priority="low")],
            issues=[IssueItem(title="a", body="b", labels=["c"])],
            dispatches=[DispatchItem(change="d")],
        )

        serialized = plan.model_dump_json()
        restored = LeadPlan.model_validate_json(serialized)

        assert restored.summary == plan.summary
        assert len(restored.proposals) == 1
        assert restored.proposals[0].name == "x"
        assert len(restored.issues) == 1
        assert restored.issues[0].title == "a"
        assert len(restored.dispatches) == 1
        assert restored.dispatches[0].change == "d"

    def test_parse_plan_with_json_in_markdown_fences(self) -> None:
        """Plan JSON inside markdown fences is extracted correctly."""
        plan_data = {
            "summary": "Fenced plan",
            "proposals": [],
            "issues": [],
            "dispatches": [],
        }
        result_text = f"Here is my plan:\n\n```json\n{json.dumps(plan_data)}\n```"
        raw = json.dumps({"result": result_text})

        plan = parse_lead_plan(raw)

        assert plan.summary == "Fenced plan"

    def test_parse_plan_with_error_field(self) -> None:
        """Error output from dispatch is handled gracefully."""
        raw = json.dumps({"error": "Claude CLI timed out"})

        plan = parse_lead_plan(raw)

        assert isinstance(plan, LeadPlan)
        # result field is empty string, so we get an empty plan
        assert plan.summary == ""


# ---------------------------------------------------------------------------
# Task 5.4: CLI command tests
# ---------------------------------------------------------------------------


class TestLeadCLI:
    def test_help_shows_lead_command(self) -> None:
        """--help includes the lead command with interactive flag."""
        import re

        result = runner.invoke(app, ["lead", "--help"])
        assert result.exit_code == 0
        # Strip ANSI escape codes before checking — Typer's rich output
        # splits flags across escape sequences (e.g., --repo becomes
        # \x1b[1;36m-\x1b[0m\x1b[1;36m-repo\x1b[0m)
        plain = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
        assert "lead" in plain.lower()
        assert "--repo" in plain
        assert "--interactive" in plain

    def test_lead_with_mock_dispatch(self, tmp_path: Path) -> None:
        """Lead command with --no-interactive returns formatted plan."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()

        plan_data = {
            "summary": "Test plan summary",
            "proposals": [
                {"name": "improve-tests", "description": "More tests", "priority": "high"}
            ],
            "issues": [],
            "dispatches": [],
        }
        mock_output = json.dumps({"result": json.dumps(plan_data)})

        with (
            patch("action_harness.cli.shutil.which", return_value="/usr/bin/mock"),
            patch(
                "action_harness.lead.dispatch_lead",
                return_value=mock_output,
            ),
            patch("action_harness.lead._gather_issues", return_value=None),
        ):
            result = runner.invoke(app, ["lead", "--repo", str(repo), "--no-interactive"])

        assert result.exit_code == 0
        assert "Test plan summary" in result.output
        assert "improve-tests" in result.output

    def test_dispatch_with_existing_change(self, tmp_path: Path) -> None:
        """--dispatch with existing change triggers subprocess."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()
        change_dir = repo / "openspec" / "changes" / "my-change"
        change_dir.mkdir(parents=True)
        (change_dir / "tasks.md").write_text("- [ ] Do something")

        plan_data = {
            "summary": "Dispatch test",
            "proposals": [],
            "issues": [],
            "dispatches": [{"change": "my-change"}],
        }
        mock_output = json.dumps({"result": json.dumps(plan_data)})

        dispatch_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with (
            patch("action_harness.cli.shutil.which", return_value="/usr/bin/mock"),
            patch(
                "action_harness.lead.dispatch_lead",
                return_value=mock_output,
            ),
            patch("action_harness.lead._gather_issues", return_value=None),
            patch(
                "action_harness.cli.subprocess.run", return_value=dispatch_result
            ) as mock_dispatch_run,
        ):
            result = runner.invoke(app, ["lead", "--repo", str(repo), "--dispatch"])

        assert result.exit_code == 0
        assert "my-change" in result.output
        # Verify harness run was called (among other subprocess calls from assessment)
        harness_calls = [
            c for c in mock_dispatch_run.call_args_list if c[0][0][0] == "action-harness"
        ]
        assert len(harness_calls) == 1
        call_cmd = harness_calls[0][0][0]
        assert "run" in call_cmd
        assert "--change" in call_cmd
        assert "my-change" in call_cmd

    def test_interactive_is_default(self, tmp_path: Path) -> None:
        """Default mode (no flags) dispatches interactively."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()

        with (
            patch("action_harness.cli.shutil.which", return_value="/usr/bin/mock"),
            patch("action_harness.lead._gather_issues", return_value=None),
            patch(
                "action_harness.lead.dispatch_lead_interactive",
                return_value=0,
            ) as mock_interactive,
            # Verify one-shot path is NOT called (routes are mutually exclusive)
            patch("action_harness.lead.dispatch_lead") as mock_oneshot,
        ):
            result = runner.invoke(app, ["lead", "--repo", str(repo)])

        assert mock_interactive.called
        mock_oneshot.assert_not_called()
        assert result.exit_code == 0

    def test_no_interactive_uses_one_shot(self, tmp_path: Path) -> None:
        """--no-interactive dispatches via one-shot mode."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()

        plan_data = {
            "summary": "Non-interactive plan",
            "proposals": [],
            "issues": [],
            "dispatches": [],
        }
        mock_output = json.dumps({"result": json.dumps(plan_data)})

        with (
            patch("action_harness.cli.shutil.which", return_value="/usr/bin/mock"),
            patch("action_harness.lead._gather_issues", return_value=None),
            patch(
                "action_harness.lead.dispatch_lead",
                return_value=mock_output,
            ) as mock_dispatch,
            # Verify interactive path is NOT called (routes are mutually exclusive)
            patch("action_harness.lead.dispatch_lead_interactive") as mock_interactive,
        ):
            result = runner.invoke(app, ["lead", "--repo", str(repo), "--no-interactive"])

        assert mock_dispatch.called
        mock_interactive.assert_not_called()
        assert result.exit_code == 0
        assert "Non-interactive plan" in result.output

    def test_dispatch_implies_no_interactive(self, tmp_path: Path) -> None:
        """--dispatch automatically sets non-interactive mode."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()

        plan_data = {
            "summary": "Dispatch test",
            "proposals": [],
            "issues": [],
            "dispatches": [],
        }
        mock_output = json.dumps({"result": json.dumps(plan_data)})

        with (
            patch("action_harness.cli.shutil.which", return_value="/usr/bin/mock"),
            patch("action_harness.lead._gather_issues", return_value=None),
            patch(
                "action_harness.lead.dispatch_lead",
                return_value=mock_output,
            ) as mock_dispatch,
            # Verify interactive path is NOT called (routes are mutually exclusive)
            patch("action_harness.lead.dispatch_lead_interactive") as mock_interactive,
        ):
            result = runner.invoke(app, ["lead", "--repo", str(repo), "--dispatch"])

        # Should use one-shot dispatch, not interactive
        assert mock_dispatch.called
        mock_interactive.assert_not_called()
        assert result.exit_code == 0

    def test_interactive_and_dispatch_errors(self, tmp_path: Path) -> None:
        """--interactive and --dispatch together produce an error."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()

        result = runner.invoke(app, ["lead", "--repo", str(repo), "--interactive", "--dispatch"])

        assert result.exit_code == 1
        assert "--interactive and --dispatch are mutually exclusive" in result.output

    def test_interactive_nonzero_exit_propagates(self, tmp_path: Path) -> None:
        """Non-zero exit code from interactive session propagates through CLI."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()

        with (
            patch("action_harness.cli.shutil.which", return_value="/usr/bin/mock"),
            patch("action_harness.lead._gather_issues", return_value=None),
            patch(
                "action_harness.lead.dispatch_lead_interactive",
                return_value=1,
            ),
        ):
            result = runner.invoke(app, ["lead", "--repo", str(repo)])

        assert result.exit_code == 1

    def test_dispatch_with_nonexistent_change_skips(self, tmp_path: Path) -> None:
        """--dispatch with nonexistent change logs warning and skips."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()

        plan_data = {
            "summary": "Skip test",
            "proposals": [],
            "issues": [],
            "dispatches": [{"change": "nonexistent-change"}],
        }
        mock_output = json.dumps({"result": json.dumps(plan_data)})

        with (
            patch("action_harness.cli.shutil.which", return_value="/usr/bin/mock"),
            patch(
                "action_harness.lead.dispatch_lead",
                return_value=mock_output,
            ),
            patch("action_harness.lead._gather_issues", return_value=None),
        ):
            result = runner.invoke(app, ["lead", "--repo", str(repo), "--dispatch"])

        assert result.exit_code == 0
        # Should show the dispatch in the plan
        assert "nonexistent-change" in result.output
        # Should show failure in dispatch results
        assert "no tasks.md" in result.output


# ---------------------------------------------------------------------------
# Prior acknowledged: _gather_issues direct tests
# ---------------------------------------------------------------------------


class TestGatherIssues:
    def test_normal_gh_output(self, tmp_path: Path) -> None:
        """_gather_issues parses normal gh JSON output."""
        gh_output = json.dumps(
            [
                {
                    "title": "Bug: login fails",
                    "body": "Login times out after 30s",
                    "labels": [{"name": "bug"}],
                },
                {
                    "title": "Feature request",
                    "body": "Add dark mode",
                    "labels": [{"name": "enhancement"}, {"name": "ui"}],
                },
            ]
        )
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=gh_output, stderr=""
        )
        with patch("action_harness.lead.subprocess.run", return_value=mock_result):
            result = _gather_issues(tmp_path, 3000)

        assert result is not None
        assert "Bug: login fails" in result
        assert "[bug]" in result
        assert "Feature request" in result
        assert "enhancement" in result

    def test_empty_issue_list(self, tmp_path: Path) -> None:
        """Empty issue list returns None."""
        mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="[]", stderr="")
        with patch("action_harness.lead.subprocess.run", return_value=mock_result):
            result = _gather_issues(tmp_path, 3000)

        assert result is None

    def test_labels_as_strings(self, tmp_path: Path) -> None:
        """Labels can be plain strings (not dicts)."""
        gh_output = json.dumps(
            [
                {"title": "Test", "body": "", "labels": ["bug", "p1"]},
            ]
        )
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=gh_output, stderr=""
        )
        with patch("action_harness.lead.subprocess.run", return_value=mock_result):
            result = _gather_issues(tmp_path, 3000)

        assert result is not None
        assert "[bug, p1]" in result

    def test_body_truncation(self, tmp_path: Path) -> None:
        """Issue bodies longer than 500 chars are truncated."""
        long_body = "x" * 600
        gh_output = json.dumps(
            [
                {"title": "Long issue", "body": long_body, "labels": []},
            ]
        )
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=gh_output, stderr=""
        )
        with patch("action_harness.lead.subprocess.run", return_value=mock_result):
            result = _gather_issues(tmp_path, 3000)

        assert result is not None
        # Body should be truncated to 500 + "..."
        assert "x" * 500 + "..." in result
        assert "x" * 501 not in result

    def test_gh_failure_returns_none(self, tmp_path: Path) -> None:
        """Non-zero gh exit returns None."""
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="auth required"
        )
        with patch("action_harness.lead.subprocess.run", return_value=mock_result):
            result = _gather_issues(tmp_path, 3000)

        assert result is None

    def test_malformed_entries_skipped(self, tmp_path: Path) -> None:
        """Non-dict entries in the list are skipped."""
        gh_output = json.dumps(
            [
                "not a dict",
                {"title": "Valid issue", "body": "ok", "labels": []},
            ]
        )
        mock_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=gh_output, stderr=""
        )
        with patch("action_harness.lead.subprocess.run", return_value=mock_result):
            result = _gather_issues(tmp_path, 3000)

        assert result is not None
        assert "Valid issue" in result

    def test_cwd_is_repo_path(self, tmp_path: Path) -> None:
        """gh is invoked with cwd=repo_path."""
        mock_result = subprocess.CompletedProcess(args=[], returncode=0, stdout="[]", stderr="")
        with patch("action_harness.lead.subprocess.run", return_value=mock_result) as mock_run:
            _gather_issues(tmp_path, 3000)

        assert mock_run.call_args.kwargs.get("cwd") == tmp_path


# ---------------------------------------------------------------------------
# Prior acknowledged: dispatch_lead non-zero exit
# ---------------------------------------------------------------------------


class TestDispatchLeadEdgeCases:
    def test_missing_agent_file_returns_error(self, tmp_path: Path) -> None:
        """Missing lead.md agent file returns error JSON, doesn't crash."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        # Intentionally no lead.md file

        output = dispatch_lead(
            repo_path=repo_path,
            prompt="test",
            context="ctx",
            harness_agents_dir=agents_dir,
        )

        data = json.loads(output)
        assert "error" in data
        assert "not found" in data["error"].lower()

    def test_nonzero_exit_returns_error(self, tmp_path: Path) -> None:
        """Claude CLI non-zero exit returns error JSON."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "lead.md").write_text("---\nname: lead\n---\nPersona")

        mock_result = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="model not found"
        )
        with patch("action_harness.lead.subprocess.run", return_value=mock_result):
            output = dispatch_lead(
                repo_path=repo_path,
                prompt="test",
                context="ctx",
                harness_agents_dir=agents_dir,
            )

        data = json.loads(output)
        assert "error" in data
        assert "exit" in data["error"].lower()
        assert "model not found" in data["error"]


# ---------------------------------------------------------------------------
# Prior acknowledged: parse_lead_plan with valid JSON but invalid schema
# ---------------------------------------------------------------------------


class TestParseLeadPlanInvalidSchema:
    def test_valid_json_invalid_schema_returns_empty(self) -> None:
        """JSON that's valid but doesn't match LeadPlan returns empty plan."""
        # proposals should be a list of objects, not a string
        bad_data = {"summary": "ok", "proposals": "not a list"}
        raw = json.dumps({"result": json.dumps(bad_data)})

        plan = parse_lead_plan(raw)

        assert isinstance(plan, LeadPlan)
        # Should fall back to empty plan since model_validate fails
        assert plan.proposals == []
