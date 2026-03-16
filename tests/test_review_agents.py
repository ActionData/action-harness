"""Tests for review agent dispatch, parsing, triage, and feedback."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from action_harness.agents import resolve_harness_agents_dir
from action_harness.models import AcknowledgedFinding, ReviewFinding, ReviewResult
from action_harness.review_agents import (
    _AGENTS_WITH_CUSTOM_SEVERITY,
    _GENERIC_SEVERITY_SUFFIX,
    REVIEW_AGENT_NAMES,
    SPEC_COMPLIANCE_AGENT_NAME,
    _titles_overlap,
    build_review_prompt,
    compute_finding_priority,
    dispatch_review_agents,
    dispatch_single_review,
    filter_actionable_findings,
    format_review_feedback,
    match_findings,
    parse_review_findings,
    select_top_findings,
    triage_findings,
)

# Resolve harness agents dir once for all tests in this module.
# Use an empty repo path so all lookups fall through to harness defaults.
_HARNESS_AGENTS_DIR = resolve_harness_agents_dir()
_EMPTY_REPO = Path("/tmp/nonexistent-repo-for-test")


class TestBuildReviewPrompt:
    def test_returns_nonempty_for_each_agent(self) -> None:
        for name in REVIEW_AGENT_NAMES:
            prompt = build_review_prompt(name, 42, _EMPTY_REPO, _HARNESS_AGENTS_DIR)
            assert len(prompt) > 0

    def test_contains_json_output_instructions(self) -> None:
        for name in REVIEW_AGENT_NAMES:
            prompt = build_review_prompt(name, 99, _EMPTY_REPO, _HARNESS_AGENTS_DIR)
            assert '"findings"' in prompt
            assert '"severity"' in prompt

    def test_unknown_agent_raises(self) -> None:
        with pytest.raises(FileNotFoundError, match="nonexistent-agent"):
            build_review_prompt("nonexistent-agent", 1, _EMPTY_REPO, _HARNESS_AGENTS_DIR)

    def test_prompt_contains_pr_number(self) -> None:
        prompt = build_review_prompt("bug-hunter", 123, _EMPTY_REPO, _HARNESS_AGENTS_DIR)
        assert "123" in prompt

    def test_bug_hunter_prompt_content(self) -> None:
        prompt = build_review_prompt("bug-hunter", 1, _EMPTY_REPO, _HARNESS_AGENTS_DIR)
        assert "bug" in prompt.lower() or "Bug" in prompt

    def test_test_reviewer_prompt_content(self) -> None:
        prompt = build_review_prompt("test-reviewer", 1, _EMPTY_REPO, _HARNESS_AGENTS_DIR)
        assert "test" in prompt.lower()

    def test_quality_reviewer_prompt_content(self) -> None:
        prompt = build_review_prompt("quality-reviewer", 1, _EMPTY_REPO, _HARNESS_AGENTS_DIR)
        assert "quality" in prompt.lower() or "maintainability" in prompt.lower()

    def test_spec_compliance_reviewer_prompt_contains_tasks_and_compliance(self) -> None:
        prompt = build_review_prompt(
            "spec-compliance-reviewer", 42, _EMPTY_REPO, _HARNESS_AGENTS_DIR
        )
        assert "tasks" in prompt.lower()
        assert "compliance" in prompt.lower()

    def test_spec_compliance_reviewer_prompt_contains_severity_definitions(self) -> None:
        prompt = build_review_prompt(
            "spec-compliance-reviewer", 42, _EMPTY_REPO, _HARNESS_AGENTS_DIR
        )
        assert "critical" in prompt.lower()
        assert "high" in prompt.lower()
        assert "medium" in prompt.lower()
        assert "low" in prompt.lower()

    def test_spec_compliance_reviewer_prompt_contains_pr_number(self) -> None:
        prompt = build_review_prompt(
            "spec-compliance-reviewer", 99, _EMPTY_REPO, _HARNESS_AGENTS_DIR
        )
        assert "99" in prompt

    def test_spec_compliance_reviewer_excludes_generic_severity(self) -> None:
        """The spec-compliance-reviewer defines its own severity scale and must
        NOT receive the generic severity definitions from _GENERIC_SEVERITY_SUFFIX."""
        prompt = build_review_prompt(
            "spec-compliance-reviewer", 42, _EMPTY_REPO, _HARNESS_AGENTS_DIR
        )
        assert _GENERIC_SEVERITY_SUFFIX.strip() not in prompt

    def test_base_agents_include_generic_severity(self) -> None:
        for name in REVIEW_AGENT_NAMES:
            prompt = build_review_prompt(name, 1, _EMPTY_REPO, _HARNESS_AGENTS_DIR)
            assert "data loss" in prompt, f"{name} prompt missing generic severity"

    def test_review_agent_names_have_agent_files(self) -> None:
        """Every REVIEW_AGENT_NAMES entry must have a loadable agent file."""
        for name in REVIEW_AGENT_NAMES:
            prompt = build_review_prompt(name, 1, _EMPTY_REPO, _HARNESS_AGENTS_DIR)
            assert len(prompt) > 0

    def test_custom_severity_agents_have_agent_files(self) -> None:
        """Every agent in _AGENTS_WITH_CUSTOM_SEVERITY must have a loadable prompt."""
        for name in _AGENTS_WITH_CUSTOM_SEVERITY:
            prompt = build_review_prompt(name, 1, _EMPTY_REPO, _HARNESS_AGENTS_DIR)
            assert len(prompt) > 0

    def test_python_ecosystem_includes_catalog_checklist(self) -> None:
        prompt = build_review_prompt(
            "bug-hunter", 42, _EMPTY_REPO, _HARNESS_AGENTS_DIR, ecosystem="python"
        )
        assert "## Catalog Checklist" in prompt
        # Should include Python-specific entries
        assert "subprocess-timeout" in prompt

    def test_no_matching_entries_no_checklist_section(self) -> None:
        """With a mock returning no entries, no checklist section added."""
        with patch(
            "action_harness.review_agents.load_catalog",
            return_value=[],
        ):
            prompt = build_review_prompt(
                "bug-hunter", 42, _EMPTY_REPO, _HARNESS_AGENTS_DIR, ecosystem="nonexistent"
            )
        assert "## Catalog Checklist" not in prompt

    def test_build_review_prompt_end_to_end(self, tmp_path: Path) -> None:
        """6.7: End-to-end test with a real agent file."""
        harness_dir = tmp_path / "agents"
        harness_dir.mkdir()
        (harness_dir / "bug-hunter.md").write_text(
            "---\nname: bug-hunter\n---\nReview PR #{pr_number} for bugs"
        )
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        prompt = build_review_prompt("bug-hunter", 42, repo_path, harness_dir, ecosystem="python")

        assert "Review PR #42 for bugs" in prompt
        assert '"findings"' in prompt  # JSON output format
        assert "data loss" in prompt  # Generic severity suffix

    def test_build_review_prompt_custom_severity_agent(self, tmp_path: Path) -> None:
        """6.8: Custom severity agent gets JSON format but not generic severity."""
        harness_dir = tmp_path / "agents"
        harness_dir.mkdir()
        (harness_dir / "spec-compliance-reviewer.md").write_text(
            "---\nname: spec-compliance-reviewer\n---\nReview compliance for PR #{pr_number}"
        )
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        prompt = build_review_prompt("spec-compliance-reviewer", 42, repo_path, harness_dir)

        assert '"findings"' in prompt  # JSON format present
        assert _GENERIC_SEVERITY_SUFFIX.strip() not in prompt  # No generic severity


class TestParseReviewFindings:
    def test_valid_json_with_findings(self) -> None:
        findings_json = {
            "findings": [
                {
                    "title": "Off-by-one",
                    "file": "src/foo.py",
                    "line": 42,
                    "severity": "high",
                    "description": "Loop bound is wrong",
                }
            ],
            "summary": "Found one issue",
        }
        raw = json.dumps({"result": json.dumps(findings_json), "cost_usd": 0.05})
        result = parse_review_findings(raw, "bug-hunter", 5.0)

        assert result.success is True
        assert result.agent_name == "bug-hunter"
        assert len(result.findings) == 1
        assert result.findings[0].title == "Off-by-one"
        assert result.findings[0].file == "src/foo.py"
        assert result.findings[0].line == 42
        assert result.findings[0].severity == "high"
        assert result.findings[0].agent == "bug-hunter"
        assert result.cost_usd == 0.05
        assert result.duration_seconds == 5.0

    def test_empty_findings_list(self) -> None:
        findings_json = {"findings": [], "summary": "No issues."}
        raw = json.dumps({"result": json.dumps(findings_json)})
        result = parse_review_findings(raw, "test-reviewer", 3.0)

        assert result.success is True
        assert result.findings == []
        assert result.agent_name == "test-reviewer"

    def test_unparseable_output(self) -> None:
        result = parse_review_findings("not json at all", "quality-reviewer", 1.0)

        assert result.success is False
        assert "invalid JSON" in (result.error or "")
        assert result.agent_name == "quality-reviewer"

    def test_no_json_block_in_result(self) -> None:
        raw = json.dumps({"result": "Just some prose with no JSON block"})
        result = parse_review_findings(raw, "bug-hunter", 2.0)

        assert result.success is False
        assert "no JSON block" in (result.error or "")

    def test_agent_field_set_on_each_finding(self) -> None:
        findings_json = {
            "findings": [
                {
                    "title": "A",
                    "file": "a.py",
                    "severity": "low",
                    "description": "d1",
                },
                {
                    "title": "B",
                    "file": "b.py",
                    "severity": "medium",
                    "description": "d2",
                },
            ],
            "summary": "Two findings",
        }
        raw = json.dumps({"result": json.dumps(findings_json)})
        result = parse_review_findings(raw, "test-reviewer", 4.0)

        assert result.success is True
        assert all(f.agent == "test-reviewer" for f in result.findings)

    def test_json_embedded_in_prose(self) -> None:
        findings_json = {
            "findings": [
                {
                    "title": "Issue",
                    "file": "x.py",
                    "severity": "critical",
                    "description": "bad",
                }
            ],
            "summary": "Found issue",
        }
        result_text = f"Here is my review:\n```json\n{json.dumps(findings_json)}\n```\nDone."
        raw = json.dumps({"result": result_text})
        result = parse_review_findings(raw, "bug-hunter", 2.0)

        assert result.success is True
        assert len(result.findings) == 1
        assert result.findings[0].severity == "critical"


class TestTriageFindings:
    def test_critical_returns_true(self) -> None:
        finding = ReviewFinding(
            title="Crash",
            file="f.py",
            severity="critical",
            description="d",
            agent="bug-hunter",
        )
        result = ReviewResult(success=True, agent_name="bug-hunter", findings=[finding])
        assert triage_findings([result]) is True

    def test_high_returns_true(self) -> None:
        finding = ReviewFinding(
            title="Bug",
            file="f.py",
            severity="high",
            description="d",
            agent="bug-hunter",
        )
        result = ReviewResult(success=True, agent_name="bug-hunter", findings=[finding])
        assert triage_findings([result]) is True

    def test_medium_returns_true(self) -> None:
        findings = [
            ReviewFinding(
                title="Style",
                file="f.py",
                severity="medium",
                description="d",
                agent="quality-reviewer",
            ),
        ]
        result = ReviewResult(success=True, agent_name="quality-reviewer", findings=findings)
        assert triage_findings([result]) is True

    def test_low_only_returns_true(self) -> None:
        finding = ReviewFinding(
            title="Nit",
            file="g.py",
            severity="low",
            description="d",
            agent="quality-reviewer",
        )
        result = ReviewResult(success=True, agent_name="quality-reviewer", findings=[finding])
        assert triage_findings([result]) is True

    def test_empty_findings_returns_false(self) -> None:
        result = ReviewResult(success=True, agent_name="test-reviewer", findings=[])
        assert triage_findings([result]) is False

    def test_all_failed_returns_false(self) -> None:
        results = [
            ReviewResult(success=False, agent_name="bug-hunter", error="failed"),
            ReviewResult(success=False, agent_name="test-reviewer", error="failed"),
        ]
        assert triage_findings(results) is False

    def test_mixed_severities_with_one_high(self) -> None:
        findings = [
            ReviewFinding(
                title="Low",
                file="f.py",
                severity="low",
                description="d",
                agent="a",
            ),
            ReviewFinding(
                title="High",
                file="g.py",
                severity="high",
                description="d",
                agent="b",
            ),
        ]
        r1 = ReviewResult(success=True, agent_name="a", findings=[findings[0]])
        r2 = ReviewResult(success=True, agent_name="b", findings=[findings[1]])
        assert triage_findings([r1, r2]) is True


class TestFormatReviewFeedback:
    def test_contains_finding_details(self) -> None:
        finding = ReviewFinding(
            title="Off-by-one",
            file="src/foo.py",
            line=42,
            severity="high",
            description="Loop bound is wrong",
            agent="bug-hunter",
        )
        result = ReviewResult(success=True, agent_name="bug-hunter", findings=[finding])
        feedback = format_review_feedback([result])

        assert "Off-by-one" in feedback
        assert "src/foo.py:42" in feedback
        assert "HIGH" in feedback
        assert "bug-hunter" in feedback

    def test_all_severities_included(self) -> None:
        findings = [
            ReviewFinding(
                title="Critical Bug",
                file="a.py",
                severity="critical",
                description="crash",
                agent="bug-hunter",
            ),
            ReviewFinding(
                title="Minor Style",
                file="b.py",
                severity="low",
                description="naming",
                agent="quality-reviewer",
            ),
        ]
        r1 = ReviewResult(success=True, agent_name="bug-hunter", findings=[findings[0]])
        r2 = ReviewResult(success=True, agent_name="quality-reviewer", findings=[findings[1]])
        feedback = format_review_feedback([r1, r2])

        assert "Critical Bug" in feedback
        assert "Minor Style" in feedback
        assert "CRITICAL" in feedback
        assert "LOW" in feedback

    def test_empty_input_no_findings_message(self) -> None:
        feedback = format_review_feedback([])
        assert "No findings" in feedback

    def test_medium_included_in_feedback(self) -> None:
        finding = ReviewFinding(
            title="Nit",
            file="x.py",
            severity="medium",
            description="d",
            agent="a",
        )
        result = ReviewResult(success=True, agent_name="a", findings=[finding])
        feedback = format_review_feedback([result])
        assert "Nit" in feedback
        assert "MEDIUM" in feedback

    def test_contains_footer(self) -> None:
        finding = ReviewFinding(
            title="Bug",
            file="f.py",
            severity="high",
            description="d",
            agent="a",
        )
        result = ReviewResult(success=True, agent_name="a", findings=[finding])
        feedback = format_review_feedback([result])
        assert "Fix the issues above" in feedback


class TestDispatchSingleReview:
    def test_command_construction(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(
            {
                "result": json.dumps({"findings": [], "summary": "ok"}),
                "cost_usd": 0.02,
            }
        )
        mock_result.stderr = ""

        with patch(
            "action_harness.review_agents.subprocess.run",
            return_value=mock_result,
        ) as mock_run:
            result = dispatch_single_review(
                "bug-hunter",
                pr_number=42,
                worktree_path=Path("/tmp/wt"),
                repo_path=_EMPTY_REPO,
                harness_agents_dir=_HARNESS_AGENTS_DIR,
                max_turns=30,
            )

        assert result.success is True
        assert result.agent_name == "bug-hunter"

        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert cmd[0] == "claude"
        assert "-p" in cmd
        assert "--output-format" in cmd
        assert "json" in cmd
        assert "--max-turns" in cmd
        assert "30" in cmd
        assert "--system-prompt" in cmd
        assert call_args[1]["cwd"] == Path("/tmp/wt")

    def test_with_optional_flags(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"result": json.dumps({"findings": [], "summary": "ok"})})
        mock_result.stderr = ""

        with patch(
            "action_harness.review_agents.subprocess.run",
            return_value=mock_result,
        ) as mock_run:
            dispatch_single_review(
                "test-reviewer",
                pr_number=10,
                worktree_path=Path("/tmp/wt"),
                repo_path=_EMPTY_REPO,
                harness_agents_dir=_HARNESS_AGENTS_DIR,
                model="opus",
                effort="high",
                max_budget_usd=1.5,
            )

        cmd = mock_run.call_args[0][0]
        assert "--model" in cmd
        assert "opus" in cmd
        assert "--effort" in cmd
        assert "high" in cmd
        assert "--max-budget-usd" in cmd
        assert "1.5" in cmd

    def test_cli_failure_returns_error_result(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "some error"

        with patch(
            "action_harness.review_agents.subprocess.run",
            return_value=mock_result,
        ):
            result = dispatch_single_review(
                "bug-hunter",
                pr_number=1,
                worktree_path=Path("/tmp/wt"),
                repo_path=_EMPTY_REPO,
                harness_agents_dir=_HARNESS_AGENTS_DIR,
            )

        assert result.success is False
        assert "exit" in (result.error or "").lower() or "exited" in (result.error or "").lower()

    def test_parsed_into_review_result(self) -> None:
        findings_json = {
            "findings": [
                {
                    "title": "Bug",
                    "file": "f.py",
                    "line": 10,
                    "severity": "high",
                    "description": "desc",
                }
            ],
            "summary": "One bug",
        }
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"result": json.dumps(findings_json), "cost_usd": 0.03})
        mock_result.stderr = ""

        with patch(
            "action_harness.review_agents.subprocess.run",
            return_value=mock_result,
        ):
            result = dispatch_single_review(
                "bug-hunter",
                pr_number=5,
                worktree_path=Path("/tmp/wt"),
                repo_path=_EMPTY_REPO,
                harness_agents_dir=_HARNESS_AGENTS_DIR,
            )

        assert isinstance(result, ReviewResult)
        assert result.success is True
        assert len(result.findings) == 1
        assert result.findings[0].title == "Bug"
        assert result.cost_usd == 0.03

    def test_extra_context_included_in_user_prompt(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"result": json.dumps({"findings": [], "summary": "ok"})})
        mock_result.stderr = ""

        with patch(
            "action_harness.review_agents.subprocess.run",
            return_value=mock_result,
        ) as mock_run:
            dispatch_single_review(
                "spec-compliance-reviewer",
                pr_number=42,
                worktree_path=Path("/tmp/wt"),
                repo_path=_EMPTY_REPO,
                harness_agents_dir=_HARNESS_AGENTS_DIR,
                extra_context="sentinel text",
            )

        cmd = mock_run.call_args[0][0]
        # The user prompt is the argument after "-p"
        p_index = cmd.index("-p")
        user_prompt = cmd[p_index + 1]
        assert "sentinel text" in user_prompt
        assert "Review PR #42" in user_prompt

    def test_extra_context_empty_string_still_appended(self) -> None:
        """Empty string extra_context is still appended (not treated as None)."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"result": json.dumps({"findings": [], "summary": "ok"})})
        mock_result.stderr = ""

        with patch(
            "action_harness.review_agents.subprocess.run",
            return_value=mock_result,
        ) as mock_run:
            dispatch_single_review(
                "spec-compliance-reviewer",
                pr_number=42,
                worktree_path=Path("/tmp/wt"),
                repo_path=_EMPTY_REPO,
                harness_agents_dir=_HARNESS_AGENTS_DIR,
                extra_context="",
            )

        cmd = mock_run.call_args[0][0]
        p_index = cmd.index("-p")
        user_prompt = cmd[p_index + 1]
        # Empty string is truthy for `is not None`, so it gets appended
        assert user_prompt == "Review PR #42\n\n"

    def test_extra_context_none_unchanged_user_prompt(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"result": json.dumps({"findings": [], "summary": "ok"})})
        mock_result.stderr = ""

        with patch(
            "action_harness.review_agents.subprocess.run",
            return_value=mock_result,
        ) as mock_run:
            dispatch_single_review(
                "bug-hunter",
                pr_number=42,
                worktree_path=Path("/tmp/wt"),
                repo_path=_EMPTY_REPO,
                harness_agents_dir=_HARNESS_AGENTS_DIR,
                extra_context=None,
            )

        cmd = mock_run.call_args[0][0]
        p_index = cmd.index("-p")
        user_prompt = cmd[p_index + 1]
        assert user_prompt == "Review PR #42"


class TestDispatchReviewAgents:
    def test_dispatches_three_agents(self) -> None:
        mock_result = ReviewResult(success=True, agent_name="mock", findings=[])

        with patch(
            "action_harness.review_agents.dispatch_single_review",
            return_value=mock_result,
        ) as mock_dispatch:
            results = dispatch_review_agents(
                pr_number=42,
                worktree_path=Path("/tmp/wt"),
                repo_path=_EMPTY_REPO,
                harness_agents_dir=_HARNESS_AGENTS_DIR,
            )

        assert len(results) == 3
        assert mock_dispatch.call_count == 3

    def test_collects_all_results(self) -> None:
        def mock_dispatch(agent_name: str, **kwargs: object) -> ReviewResult:
            return ReviewResult(success=True, agent_name=agent_name, findings=[])

        with patch(
            "action_harness.review_agents.dispatch_single_review",
            side_effect=mock_dispatch,
        ):
            results = dispatch_review_agents(
                pr_number=10,
                worktree_path=Path("/tmp/wt"),
                repo_path=_EMPTY_REPO,
                harness_agents_dir=_HARNESS_AGENTS_DIR,
            )

        agent_names = {r.agent_name for r in results}
        assert agent_names == {"bug-hunter", "test-reviewer", "quality-reviewer"}

    def test_individual_failure_does_not_block_others(self) -> None:
        call_count = {"n": 0}

        def mock_dispatch(agent_name: str, **kwargs: object) -> ReviewResult:
            call_count["n"] += 1
            if agent_name == "bug-hunter":
                return ReviewResult(
                    success=False,
                    agent_name=agent_name,
                    error="failed",
                )
            return ReviewResult(success=True, agent_name=agent_name, findings=[])

        with patch(
            "action_harness.review_agents.dispatch_single_review",
            side_effect=mock_dispatch,
        ):
            results = dispatch_review_agents(
                pr_number=1,
                worktree_path=Path("/tmp/wt"),
                repo_path=_EMPTY_REPO,
                harness_agents_dir=_HARNESS_AGENTS_DIR,
            )

        assert len(results) == 3
        assert call_count["n"] == 3
        failed = [r for r in results if not r.success]
        assert len(failed) == 1
        assert failed[0].agent_name == "bug-hunter"

    def test_change_name_with_tasks_md_dispatches_four_agents(self, tmp_path: Path) -> None:
        """change_name set + tasks.md exists → 4 agents including spec-compliance-reviewer."""
        tasks_dir = tmp_path / "openspec" / "changes" / "test-change"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "tasks.md").write_text("- [x] 99.1 sentinel task\n")

        dispatched_agents: list[str] = []
        dispatched_contexts: dict[str, str | None] = {}

        def mock_dispatch(
            agent_name: str, extra_context: str | None = None, **kwargs: object
        ) -> ReviewResult:
            dispatched_agents.append(agent_name)
            dispatched_contexts[agent_name] = extra_context
            return ReviewResult(success=True, agent_name=agent_name, findings=[])

        with patch(
            "action_harness.review_agents.dispatch_single_review",
            side_effect=mock_dispatch,
        ):
            results = dispatch_review_agents(
                pr_number=42,
                worktree_path=tmp_path,
                repo_path=_EMPTY_REPO,
                harness_agents_dir=_HARNESS_AGENTS_DIR,
                change_name="test-change",
            )

        assert len(results) == 4
        assert SPEC_COMPLIANCE_AGENT_NAME in dispatched_agents
        assert dispatched_contexts[SPEC_COMPLIANCE_AGENT_NAME] is not None
        assert "sentinel task" in (dispatched_contexts[SPEC_COMPLIANCE_AGENT_NAME] or "")
        # Other agents should NOT have extra_context
        assert dispatched_contexts["bug-hunter"] is None

    def test_change_name_none_dispatches_three_agents(self) -> None:
        """change_name=None → only 3 base agents."""
        mock_result = ReviewResult(success=True, agent_name="mock", findings=[])

        with patch(
            "action_harness.review_agents.dispatch_single_review",
            return_value=mock_result,
        ) as mock_dispatch:
            results = dispatch_review_agents(
                pr_number=42,
                worktree_path=Path("/tmp/wt"),
                repo_path=_EMPTY_REPO,
                harness_agents_dir=_HARNESS_AGENTS_DIR,
                change_name=None,
            )

        assert len(results) == 3
        assert mock_dispatch.call_count == 3

    def test_change_name_nonexistent_no_tasks_md_dispatches_three(self, tmp_path: Path) -> None:
        """change_name set but no tasks.md → only 3 base agents."""
        mock_result = ReviewResult(success=True, agent_name="mock", findings=[])

        with patch(
            "action_harness.review_agents.dispatch_single_review",
            return_value=mock_result,
        ) as mock_dispatch:
            results = dispatch_review_agents(
                pr_number=42,
                worktree_path=tmp_path,
                repo_path=_EMPTY_REPO,
                harness_agents_dir=_HARNESS_AGENTS_DIR,
                change_name="nonexistent",
            )

        assert len(results) == 3
        assert mock_dispatch.call_count == 3

    def test_tasks_md_read_failure_oserror_falls_back_to_three_agents(self, tmp_path: Path) -> None:
        """tasks.md exists but read raises OSError → graceful fallback to 3 agents."""
        tasks_dir = tmp_path / "openspec" / "changes" / "broken-change"
        tasks_dir.mkdir(parents=True)
        tasks_file = tasks_dir / "tasks.md"
        tasks_file.write_text("- [x] task")
        # Make file unreadable (targeted — only affects this specific file)
        tasks_file.chmod(0o000)

        mock_result = ReviewResult(success=True, agent_name="mock", findings=[])

        try:
            with patch(
                "action_harness.review_agents.dispatch_single_review",
                return_value=mock_result,
            ) as mock_dispatch:
                results = dispatch_review_agents(
                    pr_number=42,
                    worktree_path=tmp_path,
                    repo_path=_EMPTY_REPO,
                    harness_agents_dir=_HARNESS_AGENTS_DIR,
                    change_name="broken-change",
                )
        finally:
            # Restore permissions so tmp_path cleanup succeeds
            tasks_file.chmod(0o644)

        assert len(results) == 3
        assert mock_dispatch.call_count == 3

    def test_tasks_md_read_failure_unicode_falls_back_to_three_agents(self, tmp_path: Path) -> None:
        """tasks.md with invalid encoding → graceful fallback to 3 agents."""
        tasks_dir = tmp_path / "openspec" / "changes" / "bad-encoding"
        tasks_dir.mkdir(parents=True)
        tasks_file = tasks_dir / "tasks.md"
        # Write raw bytes that are invalid UTF-8
        tasks_file.write_bytes(b"\x80\x81\x82 invalid utf-8")

        mock_result = ReviewResult(success=True, agent_name="mock", findings=[])

        with patch(
            "action_harness.review_agents.dispatch_single_review",
            return_value=mock_result,
        ) as mock_dispatch:
            results = dispatch_review_agents(
                pr_number=42,
                worktree_path=tmp_path,
                repo_path=_EMPTY_REPO,
                harness_agents_dir=_HARNESS_AGENTS_DIR,
                change_name="bad-encoding",
            )

        assert len(results) == 3
        assert mock_dispatch.call_count == 3


def _make_finding(
    severity: str, title: str = "Finding", file: str = "f.py", agent: str = "a"
) -> ReviewFinding:
    return ReviewFinding(
        title=title,
        file=file,
        severity=severity,
        description="desc",
        agent=agent,  # type: ignore[arg-type]
    )


class TestFilterActionableFindings:
    """Task 6.1: test filter_actionable_findings at each tolerance level."""

    def test_tolerance_low_returns_all(self) -> None:
        findings = [
            _make_finding("low"),
            _make_finding("medium"),
            _make_finding("high"),
            _make_finding("critical"),
        ]
        result = ReviewResult(success=True, agent_name="a", findings=findings)
        actionable = filter_actionable_findings([result], "low")
        assert len(actionable) == 4

    def test_tolerance_med_excludes_low(self) -> None:
        findings = [
            _make_finding("low"),
            _make_finding("medium"),
            _make_finding("high"),
            _make_finding("critical"),
        ]
        result = ReviewResult(success=True, agent_name="a", findings=findings)
        actionable = filter_actionable_findings([result], "med")
        assert len(actionable) == 3
        assert all(f.severity != "low" for f in actionable)

    def test_tolerance_high_excludes_low_and_medium(self) -> None:
        findings = [
            _make_finding("low"),
            _make_finding("medium"),
            _make_finding("high"),
            _make_finding("critical"),
        ]
        result = ReviewResult(success=True, agent_name="a", findings=findings)
        actionable = filter_actionable_findings([result], "high")
        assert len(actionable) == 2
        assert {f.severity for f in actionable} == {"high", "critical"}


class TestTriageFindingsWithTolerance:
    """Task 6.2: test triage_findings with tolerance parameter."""

    def test_low_only_at_tolerance_low_returns_true(self) -> None:
        finding = _make_finding("low")
        result = ReviewResult(success=True, agent_name="a", findings=[finding])
        assert triage_findings([result], "low") is True

    def test_low_only_at_tolerance_med_returns_false(self) -> None:
        finding = _make_finding("low")
        result = ReviewResult(success=True, agent_name="a", findings=[finding])
        assert triage_findings([result], "med") is False

    def test_low_only_at_tolerance_high_returns_false(self) -> None:
        finding = _make_finding("low")
        result = ReviewResult(success=True, agent_name="a", findings=[finding])
        assert triage_findings([result], "high") is False

    def test_empty_findings_returns_false_at_all_tolerances(self) -> None:
        result = ReviewResult(success=True, agent_name="a", findings=[])
        assert triage_findings([result], "low") is False
        assert triage_findings([result], "med") is False
        assert triage_findings([result], "high") is False


class TestFormatReviewFeedbackFiltering:
    """Task 6.3: test format_review_feedback with tolerance filtering."""

    def test_med_tolerance_excludes_low(self) -> None:
        high = _make_finding("high", title="High issue")
        low1 = _make_finding("low", title="Low nit 1")
        low2 = _make_finding("low", title="Low nit 2")
        result = ReviewResult(success=True, agent_name="a", findings=[high, low1, low2])
        feedback = format_review_feedback([result], tolerance="med")
        assert "High issue" in feedback
        assert "Low nit 1" not in feedback
        assert "Low nit 2" not in feedback

    def test_prior_acknowledged_section_included(self) -> None:
        high = _make_finding("high", title="Real issue")
        result = ReviewResult(success=True, agent_name="a", findings=[high])
        ack_finding = _make_finding("medium", title="Old concern", file="old.py")
        ack = AcknowledgedFinding(finding=ack_finding, acknowledged_in_round=1)
        feedback = format_review_feedback([result], tolerance="low", prior_acknowledged=[ack])
        assert "Prior Acknowledged Findings" in feedback
        assert "Old concern" in feedback
        assert "old.py" in feedback
        assert "round 1" in feedback


class TestMatchFindings:
    """Tasks 6.5 and 6.6: test match_findings."""

    def test_title_substring_match(self) -> None:
        prior = _make_finding(
            "high",
            title="Missing null check",
            file="a.py",
            agent="bug-hunter",
        )
        current_match = _make_finding(
            "high",
            title="Missing null check on return",
            file="a.py",
            agent="quality-reviewer",
        )
        matched = match_findings([prior], [current_match])
        assert len(matched) == 1
        assert matched[0] is current_match

    def test_different_file_no_match(self) -> None:
        prior = _make_finding(
            "high",
            title="Missing null check",
            file="a.py",
            agent="bug-hunter",
        )
        current_no_match = _make_finding(
            "high",
            title="Missing null check",
            file="b.py",
            agent="bug-hunter",
        )
        matched = match_findings([prior], [current_no_match])
        assert len(matched) == 0

    def test_same_agent_same_file_matches(self) -> None:
        prior = _make_finding(
            "medium",
            title="Unused import",
            file="a.py",
            agent="quality-reviewer",
        )
        current = _make_finding(
            "medium",
            title="Unclear naming",
            file="a.py",
            agent="quality-reviewer",
        )
        matched = match_findings([prior], [current])
        assert len(matched) == 1
        assert matched[0] is current

    def test_different_agent_different_title_no_match(self) -> None:
        """Same file but different agent and non-overlapping titles → no match."""
        prior = _make_finding(
            "high",
            title="Missing null check",
            file="a.py",
            agent="bug-hunter",
        )
        current = _make_finding(
            "medium",
            title="Unclear naming convention",
            file="a.py",
            agent="quality-reviewer",
        )
        matched = match_findings([prior], [current])
        assert len(matched) == 0


class TestTitlesOverlap:
    """Direct tests for _titles_overlap helper."""

    def test_full_substring_match(self) -> None:
        assert _titles_overlap("null check", "null check missing") is True

    def test_bigram_overlap_reworded(self) -> None:
        """Shared bigram 'null check' in different word order."""
        assert _titles_overlap("null check missing in handler", "Missing null check") is True

    def test_case_insensitive(self) -> None:
        assert _titles_overlap("NULL CHECK", "null check missing") is True

    def test_single_word_titles_no_bigram_match(self) -> None:
        """Single-word titles cannot match via bigram path — only substring."""
        # "Bug" is a substring of "Debug" so this returns True via substring path.
        # But single-word vs multi-word with no substring overlap returns False.
        assert _titles_overlap("Crash", "unused import detected") is False

    def test_empty_strings(self) -> None:
        # Empty titles return False to prevent false-positive matches
        assert _titles_overlap("", "anything") is False
        assert _titles_overlap("anything", "") is False
        assert _titles_overlap("", "") is False

    def test_no_shared_bigram(self) -> None:
        """Titles share common words but not as a contiguous bigram."""
        assert _titles_overlap("missing error handling", "error in missing module") is False

    def test_completely_different_titles(self) -> None:
        assert _titles_overlap("race condition in cache", "unused import os") is False

    def test_identical_titles(self) -> None:
        assert _titles_overlap("off by one", "off by one") is True


class TestComputeFindingPriority:
    """Task 1.3: priority scoring tests."""

    def test_critical_outranks_medium_with_more_agents(self) -> None:
        """(a) critical(cross=1) priority=31 > medium(cross=3) priority=13."""
        critical = _make_finding("critical", title="Crash bug", file="f.py", agent="bug-hunter")
        # medium finding flagged by 3 agents on the same file with overlapping title
        med1 = _make_finding("medium", title="Null issue", file="g.py", agent="bug-hunter")
        med2 = _make_finding(
            "medium", title="Null issue found", file="g.py", agent="quality-reviewer"
        )
        med3 = _make_finding(
            "medium", title="Null issue detected", file="g.py", agent="test-reviewer"
        )
        all_findings = [critical, med1, med2, med3]
        assert compute_finding_priority(critical, all_findings) == 3 * 10 + 1  # 31
        assert compute_finding_priority(med1, all_findings) == 1 * 10 + 3  # 13
        assert compute_finding_priority(critical, all_findings) > compute_finding_priority(
            med1, all_findings
        )

    def test_same_severity_more_agents_ranks_higher(self) -> None:
        """(b) Two high findings: cross_agent_count=3 beats cross_agent_count=1."""
        # All three agents flag "null check" variants on foo.py — each title
        # is a substring of the next, so all three overlap with each other.
        h1 = _make_finding("high", title="Null check", file="foo.py", agent="bug-hunter")
        h1_overlap1 = _make_finding(
            "high", title="Null check missing", file="foo.py", agent="quality-reviewer"
        )
        h1_overlap2 = _make_finding(
            "high", title="Null check missing in handler", file="foo.py", agent="test-reviewer"
        )
        h2 = _make_finding("high", title="Race condition", file="bar.py", agent="bug-hunter")
        all_findings = [h1, h1_overlap1, h1_overlap2, h2]
        p1 = compute_finding_priority(h1, all_findings)
        p2 = compute_finding_priority(h2, all_findings)
        assert p1 == 2 * 10 + 3  # 23
        assert p2 == 2 * 10 + 1  # 21
        assert p1 > p2

    def test_cross_agent_with_title_overlap(self) -> None:
        """(c) Cross-agent detection: reworded titles with shared bigram overlap."""
        # Spec scenario: "null check missing in handler" and "Missing null check"
        # share the bigram "null check" — cross_agent_count should be 2 for both.
        f1 = _make_finding(
            "high",
            title="null check missing in handler",
            file="foo.py",
            agent="bug-hunter",
        )
        f2 = _make_finding(
            "high",
            title="Missing null check",
            file="foo.py",
            agent="quality-reviewer",
        )
        all_findings = [f1, f2]
        assert compute_finding_priority(f1, all_findings) == 2 * 10 + 2  # 22
        assert compute_finding_priority(f2, all_findings) == 2 * 10 + 2  # 22

    def test_no_title_overlap_no_cross_agent(self) -> None:
        """(d) Different titles on same file → cross_agent_count=1 each."""
        f1 = _make_finding("high", title="race condition", file="foo.py", agent="bug-hunter")
        f2 = _make_finding("medium", title="unused import", file="foo.py", agent="quality-reviewer")
        all_findings = [f1, f2]
        assert compute_finding_priority(f1, all_findings) == 2 * 10 + 1  # 21
        assert compute_finding_priority(f2, all_findings) == 1 * 10 + 1  # 11


class TestSelectTopFindings:
    """Task 1.3: selection tests."""

    def test_max_findings_zero_returns_all(self) -> None:
        """(e) max_findings=0 returns all as selected, empty deferred."""
        findings = [_make_finding("high"), _make_finding("medium"), _make_finding("low")]
        selected, deferred = select_top_findings(findings, max_findings=0)
        assert len(selected) == 3
        assert len(deferred) == 0

    def test_fewer_than_cap(self) -> None:
        """(f) max_findings=5 with 3 findings returns 3 selected, 0 deferred."""
        findings = [_make_finding("high"), _make_finding("medium"), _make_finding("low")]
        selected, deferred = select_top_findings(findings, max_findings=5)
        assert len(selected) == 3
        assert len(deferred) == 0

    def test_more_than_cap(self) -> None:
        """(g) max_findings=5 with 12 findings returns 5 selected, 7 deferred."""
        findings = [_make_finding("medium", title=f"Finding {i}") for i in range(12)]
        selected, deferred = select_top_findings(findings, max_findings=5)
        assert len(selected) == 5
        assert len(deferred) == 7


class TestFormatReviewFeedbackMaxFindings:
    """Task 2.2: test format_review_feedback with max_findings parameter."""

    def test_max_findings_caps_output(self) -> None:
        """max_findings=3 includes only 3 findings in output text."""
        findings = [
            _make_finding("critical", title=f"Finding {i}", agent=f"agent-{i}") for i in range(6)
        ]
        results = [
            ReviewResult(success=True, agent_name=f"agent-{i}", findings=[f])
            for i, f in enumerate(findings)
        ]
        feedback = format_review_feedback(results, max_findings=3)
        # Count how many finding titles appear in the output
        included = sum(1 for i in range(6) if f"Finding {i}" in feedback)
        assert included == 3

    def test_max_findings_zero_includes_all(self) -> None:
        """max_findings=0 includes all findings (backward compatible)."""
        findings = [_make_finding("high", title=f"Issue {i}", agent="a") for i in range(5)]
        result = ReviewResult(success=True, agent_name="a", findings=findings)
        feedback = format_review_feedback([result], max_findings=0)
        for i in range(5):
            assert f"Issue {i}" in feedback

    def test_deferred_not_in_feedback(self) -> None:
        """Deferred findings do NOT appear in the feedback text."""
        findings = [
            _make_finding("critical", title="Critical Bug", agent="a"),
            _make_finding("low", title="Minor Nit", agent="b"),
        ]
        results = [
            ReviewResult(success=True, agent_name="a", findings=[findings[0]]),
            ReviewResult(success=True, agent_name="b", findings=[findings[1]]),
        ]
        feedback = format_review_feedback(results, max_findings=1)
        assert "Critical Bug" in feedback
        assert "Minor Nit" not in feedback


class TestFormatReviewFeedbackEdgeCases:
    """Additional edge case tests for format_review_feedback."""

    def test_no_actionable_with_prior_acknowledged_drops_ack_section(self) -> None:
        """When zero actionable findings exist, prior_acknowledged section is skipped."""
        low = _make_finding("low", title="Low nit")
        result = ReviewResult(success=True, agent_name="a", findings=[low])
        ack_finding = _make_finding("medium", title="Old concern", file="old.py")
        ack = AcknowledgedFinding(finding=ack_finding, acknowledged_in_round=1)
        # At tolerance "high", the low finding is not actionable
        feedback = format_review_feedback([result], tolerance="high", prior_acknowledged=[ack])
        assert "No findings" in feedback
        assert "Prior Acknowledged Findings" not in feedback
