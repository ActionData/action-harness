"""Tests for gap proposal generation."""

import subprocess
from pathlib import Path
from unittest.mock import patch

from action_harness.assessment import Gap
from action_harness.gap_proposals import generate_proposals
from action_harness.profiler import RepoProfile


def _make_profile() -> RepoProfile:
    return RepoProfile(
        ecosystem="python",
        eval_commands=["uv run pytest -v"],
        source="convention",
    )


def _make_completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_scaffold_and_dispatch(tmp_path: Path) -> None:
    """Proposals with names trigger scaffolding and dispatch."""
    gaps = [
        Gap(
            severity="high",
            finding="No CI tests",
            category="ci_guardrails",
            proposal_name="add-ci-tests",
        ),
        Gap(
            severity="medium",
            finding="No README",
            category="context",
            proposal_name="add-readme",
        ),
    ]

    with patch("action_harness.gap_proposals.subprocess.run") as mock_run:
        mock_run.return_value = _make_completed(0)
        results = generate_proposals(gaps, tmp_path, _make_profile())

    assert len(results) == 2
    # openspec new change called for each proposal
    scaffold_calls = [
        c for c in mock_run.call_args_list
        if c[0][0][0] == "openspec"
    ]
    assert len(scaffold_calls) == 2

    # claude dispatch called for each proposal
    claude_calls = [
        c for c in mock_run.call_args_list
        if c[0][0][0] == "claude"
    ]
    assert len(claude_calls) == 2


def test_no_proposals_with_names(tmp_path: Path) -> None:
    """Gaps without proposal_name are skipped."""
    gaps = [
        Gap(severity="low", finding="Minor issue", category="context", proposal_name=None),
    ]
    results = generate_proposals(gaps, tmp_path, _make_profile())
    assert len(results) == 0


def test_failure_isolation(tmp_path: Path) -> None:
    """One spec-writer failure doesn't block others."""
    gaps = [
        Gap(severity="high", finding="Gap 1", category="ci_guardrails", proposal_name="gap-one"),
        Gap(severity="medium", finding="Gap 2", category="context", proposal_name="gap-two"),
    ]

    call_count = 0

    def side_effect(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal call_count
        call_count += 1
        # Scaffolding succeeds for both
        if cmd[0] == "openspec":
            return _make_completed(0)
        # First claude dispatch fails, second succeeds
        if cmd[0] == "claude":
            if "gap-one" in str(kwargs.get("cwd", "")):
                return _make_completed(1, stderr="failed")
            return _make_completed(0)
        return _make_completed(0)

    with patch("action_harness.gap_proposals.subprocess.run", side_effect=side_effect):
        results = generate_proposals(gaps, tmp_path, _make_profile())

    # Both should have been attempted
    assert len(results) == 2
