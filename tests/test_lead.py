"""Tests for the repo lead module: agent file, context gathering, dispatch, plan parsing."""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from action_harness.agents import parse_agent_file
from action_harness.lead import (
    DispatchItem,
    IssueItem,
    LeadPlan,
    ProposalItem,
    dispatch_lead,
    gather_lead_context,
    parse_lead_plan,
)


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
            context = gather_lead_context(tmp_path)

        assert "Roadmap" in context
        assert "First change" in context
        assert "CLAUDE.md" in context
        assert "Build instructions" in context

    def test_missing_files_skipped(self, tmp_path: Path) -> None:
        """Missing context files are skipped without error."""
        (tmp_path / ".git").mkdir()

        with patch("action_harness.lead._gather_issues", return_value=None):
            context = gather_lead_context(tmp_path)

        # Should return minimal context, not crash
        assert "context" in context.lower() or "Repo Context" in context

    def test_gh_failure_is_nonfatal(self, tmp_path: Path) -> None:
        """gh failure is non-fatal — warning logged, issues section omitted."""
        (tmp_path / ".git").mkdir()
        (tmp_path / "CLAUDE.md").write_text("# Test project")

        # Simulate gh not being available
        with patch(
            "action_harness.lead.subprocess.run",
            side_effect=FileNotFoundError("gh not found"),
        ):
            context = gather_lead_context(tmp_path)

        # Should still have CLAUDE.md content
        assert "Test project" in context
        # Should NOT have issues section
        assert "Open Issues" not in context

    def test_empty_repo_returns_minimal_context(self, tmp_path: Path) -> None:
        """Empty repo returns minimal context with a note."""
        (tmp_path / ".git").mkdir()

        with patch("action_harness.lead._gather_issues", return_value=None):
            context = gather_lead_context(tmp_path)

        assert "No context files found" in context or "Repo Context" in context

    def test_openspec_roadmap_preferred(self, tmp_path: Path) -> None:
        """openspec/ROADMAP.md is preferred over root ROADMAP.md."""
        (tmp_path / ".git").mkdir()
        (tmp_path / "ROADMAP.md").write_text("Root roadmap")
        openspec = tmp_path / "openspec"
        openspec.mkdir()
        (openspec / "ROADMAP.md").write_text("OpenSpec roadmap content")

        with patch("action_harness.lead._gather_issues", return_value=None):
            context = gather_lead_context(tmp_path)

        assert "OpenSpec roadmap content" in context

    def test_harness_md_included(self, tmp_path: Path) -> None:
        """HARNESS.md is included in context when present."""
        (tmp_path / ".git").mkdir()
        (tmp_path / "HARNESS.md").write_text("Run pytest to validate")

        with patch("action_harness.lead._gather_issues", return_value=None):
            context = gather_lead_context(tmp_path)

        assert "HARNESS.md" in context
        assert "pytest" in context


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

        mock_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="{}", stderr=""
        )

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

        mock_result = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="{}", stderr=""
        )

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
