"""Integration tests for the review agents pipeline stage."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from action_harness.models import (
    EvalResult,
    OpenSpecReviewResult,
    ReviewResult,
    WorkerResult,
)
from action_harness.openspec_reviewer import parse_review_result
from action_harness.pipeline import run_pipeline


def _approved_review_result() -> OpenSpecReviewResult:
    review_json = {
        "status": "approved",
        "tasks_total": 1,
        "tasks_complete": 1,
        "validation_passed": True,
        "semantic_review_passed": True,
        "findings": [],
        "archived": True,
    }
    raw = json.dumps({"result": json.dumps(review_json)})
    return parse_review_result(raw, 1.0)


def _passing_eval() -> EvalResult:
    return EvalResult(success=True, stage="eval", commands_run=4, commands_passed=4)


def _no_findings_review_results() -> list[ReviewResult]:
    """Three ReviewResults with no findings."""
    return [
        ReviewResult(success=True, agent_name="bug-hunter", findings=[], cost_usd=0.02),
        ReviewResult(success=True, agent_name="test-reviewer", findings=[], cost_usd=0.02),
        ReviewResult(success=True, agent_name="quality-reviewer", findings=[], cost_usd=0.02),
    ]


def _high_severity_review_results() -> list[ReviewResult]:
    """Three ReviewResults, one with a high-severity finding."""
    from action_harness.models import ReviewFinding

    finding = ReviewFinding(
        title="Off-by-one error",
        file="src/foo.py",
        line=42,
        severity="high",
        description="Loop iterates one too many times",
        agent="bug-hunter",
    )
    return [
        ReviewResult(
            success=True,
            agent_name="bug-hunter",
            findings=[finding],
            cost_usd=0.03,
        ),
        ReviewResult(success=True, agent_name="test-reviewer", findings=[], cost_usd=0.02),
        ReviewResult(success=True, agent_name="quality-reviewer", findings=[], cost_usd=0.02),
    ]


def _medium_only_review_results() -> list[ReviewResult]:
    """Three ReviewResults with only medium/low findings."""
    from action_harness.models import ReviewFinding

    finding = ReviewFinding(
        title="Style nit",
        file="src/bar.py",
        severity="medium",
        description="Naming convention",
        agent="quality-reviewer",
    )
    return [
        ReviewResult(success=True, agent_name="bug-hunter", findings=[], cost_usd=0.02),
        ReviewResult(success=True, agent_name="test-reviewer", findings=[], cost_usd=0.02),
        ReviewResult(
            success=True,
            agent_name="quality-reviewer",
            findings=[finding],
            cost_usd=0.02,
        ),
    ]


@pytest.fixture
def test_repo(tmp_path: Path) -> Path:
    """Create a temporary git repo for testing."""
    repo = tmp_path / "repo"
    repo.mkdir()

    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        capture_output=True,
        check=True,
    )

    (repo / "pyproject.toml").write_text('[project]\nname = "test"\nversion = "0.1.0"\n')
    (repo / "tests").mkdir()
    (repo / "tests" / "__init__.py").write_text("")
    (repo / "tests" / "test_basic.py").write_text("def test_ok() -> None:\n    assert True\n")

    change_dir = repo / "openspec" / "changes" / "test-change"
    change_dir.mkdir(parents=True)
    (change_dir / "tasks.md").write_text("- [ ] 1.1 Add a feature\n")

    (repo / "src").mkdir()

    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        capture_output=True,
        check=True,
    )

    return repo


def _make_claude_mock(
    commits: bool = True,
    cost: float = 0.10,
) -> MagicMock:
    """Create a mock for subprocess.run that simulates the claude CLI."""
    original_run = subprocess.run

    def side_effect(
        cmd: list[str], **kwargs: object
    ) -> MagicMock | subprocess.CompletedProcess[str]:
        if cmd[0] == "claude":
            cwd = kwargs.get("cwd")
            if commits and cwd:
                cwd_path = Path(str(cwd))
                (cwd_path / "new_feature.py").write_text("# new feature\n")
                original_run(["git", "add", "."], cwd=cwd_path, capture_output=True)
                original_run(
                    ["git", "commit", "-m", "Add feature"],
                    cwd=cwd_path,
                    capture_output=True,
                )
            result = MagicMock()
            result.returncode = 0
            result.stdout = json.dumps({"cost_usd": cost, "result": "implemented"})
            result.stderr = ""
            return result
        elif cmd[0] == "gh":
            result = MagicMock()
            result.returncode = 0
            result.stdout = "https://github.com/test/repo/pull/1"
            result.stderr = ""
            return result
        elif cmd[0] == "git" and "push" in cmd:
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result
        else:
            return original_run(cmd, **kwargs)

    return MagicMock(side_effect=side_effect)


class TestPipelineWithReviewAgents:
    def test_review_results_in_manifest(self, test_repo: Path) -> None:
        """ReviewResults appear after PrResult and before OpenSpecReviewResult."""
        mock = _make_claude_mock(commits=True)

        with (
            patch("action_harness.worker.subprocess.run", mock),
            patch("action_harness.pipeline.run_eval", return_value=_passing_eval()),
            patch("action_harness.pr.subprocess.run", mock),
            patch("action_harness.pipeline.subprocess.run", mock),
            patch(
                "action_harness.pipeline.dispatch_review_agents",
                return_value=_no_findings_review_results(),
            ),
            patch(
                "action_harness.pipeline.dispatch_openspec_review",
                return_value=('{"result": "{}"}', 1.0),
            ),
            patch(
                "action_harness.pipeline.parse_review_result",
                return_value=_approved_review_result(),
            ),
            patch(
                "action_harness.pipeline.push_archive_if_needed",
                return_value=(False, None),
            ),
        ):
            pr_result, manifest = run_pipeline("test-change", test_repo, max_retries=1)

        assert pr_result.success is True

        # Find stage indices
        review_stages = [
            (i, s) for i, s in enumerate(manifest.stages) if isinstance(s, ReviewResult)
        ]
        assert len(review_stages) == 3

        # Find PrResult and OpenSpecReviewResult indices
        from action_harness.models import PrResult as PrResultModel

        pr_indices = [i for i, s in enumerate(manifest.stages) if isinstance(s, PrResultModel)]
        openspec_indices = [
            i for i, s in enumerate(manifest.stages) if isinstance(s, OpenSpecReviewResult)
        ]

        assert len(pr_indices) == 1
        assert len(openspec_indices) == 1

        # Review stages should come after PrResult and before OpenSpecReviewResult
        for idx, _stage in review_stages:
            assert idx > pr_indices[0]
            assert idx < openspec_indices[0]

    def test_fix_retry_path(self, test_repo: Path) -> None:
        """High-severity finding triggers fix retry, second round is clean."""
        mock = _make_claude_mock(commits=True)

        # First review returns high findings, second review returns clean
        review_call_count = {"n": 0}

        def review_side_effect(**kwargs: object) -> list[ReviewResult]:
            review_call_count["n"] += 1
            if review_call_count["n"] == 1:
                return _high_severity_review_results()
            return _no_findings_review_results()

        with (
            patch("action_harness.worker.subprocess.run", mock),
            patch("action_harness.pipeline.run_eval", return_value=_passing_eval()),
            patch("action_harness.pr.subprocess.run", mock),
            patch("action_harness.pipeline.subprocess.run", mock),
            patch(
                "action_harness.pipeline.dispatch_review_agents",
                side_effect=review_side_effect,
            ),
            patch(
                "action_harness.pipeline.dispatch_openspec_review",
                return_value=('{"result": "{}"}', 1.0),
            ),
            patch(
                "action_harness.pipeline.parse_review_result",
                return_value=_approved_review_result(),
            ),
            patch(
                "action_harness.pipeline.push_archive_if_needed",
                return_value=(False, None),
            ),
        ):
            pr_result, manifest = run_pipeline("test-change", test_repo, max_retries=1)

        assert pr_result.success is True

        # Should have: worktree, worker, eval, pr, 3x review (round 1),
        # worker (fix), eval (fix), 3x review (round 2), openspec
        worker_stages = [s for s in manifest.stages if isinstance(s, WorkerResult)]
        eval_stages = [s for s in manifest.stages if isinstance(s, EvalResult)]
        review_stages = [s for s in manifest.stages if isinstance(s, ReviewResult)]

        assert len(worker_stages) == 2  # initial + fix retry
        assert len(eval_stages) == 2  # initial + fix retry
        assert len(review_stages) == 6  # 3 per round, 2 rounds

    def test_medium_triggers_retry(self, test_repo: Path) -> None:
        """Medium findings now trigger fix-retry (strict triage)."""
        mock = _make_claude_mock(commits=True)

        # First call returns medium findings, second call (after fix) returns clean
        review_call_count = {"n": 0}
        original_medium = _medium_only_review_results()
        clean = _no_findings_review_results()

        def review_side_effect(**kwargs: object) -> list[ReviewResult]:
            review_call_count["n"] += 1
            if review_call_count["n"] == 1:
                return original_medium
            return clean

        with (
            patch("action_harness.worker.subprocess.run", mock),
            patch("action_harness.pipeline.run_eval", return_value=_passing_eval()),
            patch("action_harness.pr.subprocess.run", mock),
            patch("action_harness.pipeline.subprocess.run", mock),
            patch(
                "action_harness.pipeline.dispatch_review_agents",
                side_effect=review_side_effect,
            ),
            patch(
                "action_harness.pipeline.dispatch_openspec_review",
                return_value=('{"result": "{}"}', 1.0),
            ),
            patch(
                "action_harness.pipeline.parse_review_result",
                return_value=_approved_review_result(),
            ),
            patch(
                "action_harness.pipeline.push_archive_if_needed",
                return_value=(False, None),
            ),
        ):
            pr_result, manifest = run_pipeline("test-change", test_repo, max_retries=1)

        assert pr_result.success is True

        # Should have: worktree, worker, eval, pr, 3x review (round 1),
        # worker (fix), eval (fix), 3x review (round 2), openspec
        worker_stages = [s for s in manifest.stages if isinstance(s, WorkerResult)]
        assert len(worker_stages) == 2  # initial + fix retry

    def test_two_round_cap(self, test_repo: Path) -> None:
        """After 2 fix-retry rounds with persistent findings, post comment and continue."""
        mock = _make_claude_mock(commits=True)

        # Review agents always return findings (never clean) — including
        # the verification review that runs after the loop.
        with (
            patch("action_harness.worker.subprocess.run", mock),
            patch("action_harness.pipeline.run_eval", return_value=_passing_eval()),
            patch("action_harness.pr.subprocess.run", mock),
            patch("action_harness.pipeline.subprocess.run", mock) as mock_subprocess,
            patch(
                "action_harness.pipeline.dispatch_review_agents",
                return_value=_high_severity_review_results(),
            ),
            patch(
                "action_harness.pipeline.dispatch_openspec_review",
                return_value=('{"result": "{}"}', 1.0),
            ),
            patch(
                "action_harness.pipeline.parse_review_result",
                return_value=_approved_review_result(),
            ),
            patch(
                "action_harness.pipeline.push_archive_if_needed",
                return_value=(False, None),
            ),
        ):
            pr_result, manifest = run_pipeline("test-change", test_repo, max_retries=3)

        assert pr_result.success is True

        # Should have: initial worker + 2 fix-retry workers = 3 worker dispatches
        worker_stages = [s for s in manifest.stages if isinstance(s, WorkerResult)]
        assert len(worker_stages) == 3  # initial + 2 fix-retries

        # 3 review rounds: round 1, round 2, + verification review
        review_stages = [s for s in manifest.stages if isinstance(s, ReviewResult)]
        assert len(review_stages) == 9  # 3 agents * 3 review dispatches

        # Verify a "Remaining findings" comment was posted
        gh_calls = [
            call
            for call in mock_subprocess.call_args_list
            if call[0][0][0] == "gh" and "comment" in call[0][0]
        ]
        remaining_calls = [
            call
            for call in gh_calls
            if "Remaining findings" in call[0][0][call[0][0].index("--body") + 1]
        ]
        assert len(remaining_calls) >= 1

    def test_verification_review_clears_findings(self, test_repo: Path) -> None:
        """When fix-retry resolves all findings, verification review prevents stale comment."""
        mock = _make_claude_mock(commits=True)

        # Rounds 1 and 2 return findings; verification review returns clean
        review_call_count = {"n": 0}

        def review_side_effect(**kwargs: object) -> list[ReviewResult]:
            review_call_count["n"] += 1
            if review_call_count["n"] <= 2:
                return _high_severity_review_results()
            return _no_findings_review_results()  # verification review

        with (
            patch("action_harness.worker.subprocess.run", mock),
            patch("action_harness.pipeline.run_eval", return_value=_passing_eval()),
            patch("action_harness.pr.subprocess.run", mock),
            patch("action_harness.pipeline.subprocess.run", mock) as mock_subprocess,
            patch(
                "action_harness.pipeline.dispatch_review_agents",
                side_effect=review_side_effect,
            ),
            patch(
                "action_harness.pipeline.dispatch_openspec_review",
                return_value=('{"result": "{}"}', 1.0),
            ),
            patch(
                "action_harness.pipeline.parse_review_result",
                return_value=_approved_review_result(),
            ),
            patch(
                "action_harness.pipeline.push_archive_if_needed",
                return_value=(False, None),
            ),
        ):
            pr_result, manifest = run_pipeline("test-change", test_repo, max_retries=3)

        assert pr_result.success is True

        # Still 3 worker dispatches (initial + 2 fix-retries)
        worker_stages = [s for s in manifest.stages if isinstance(s, WorkerResult)]
        assert len(worker_stages) == 3

        # No "Remaining findings" comment should be posted since verification was clean
        gh_calls = [
            call
            for call in mock_subprocess.call_args_list
            if call[0][0][0] == "gh" and "comment" in call[0][0]
        ]
        remaining_calls = [
            call
            for call in gh_calls
            if "Remaining findings" in call[0][0][call[0][0].index("--body") + 1]
        ]
        assert len(remaining_calls) == 0

    def test_review_costs_included_in_manifest(self, test_repo: Path) -> None:
        """ReviewResult costs are summed in manifest total_cost_usd."""
        mock = _make_claude_mock(commits=True, cost=0.10)

        with (
            patch("action_harness.worker.subprocess.run", mock),
            patch("action_harness.pipeline.run_eval", return_value=_passing_eval()),
            patch("action_harness.pr.subprocess.run", mock),
            patch("action_harness.pipeline.subprocess.run", mock),
            patch(
                "action_harness.pipeline.dispatch_review_agents",
                return_value=_no_findings_review_results(),
            ),
            patch(
                "action_harness.pipeline.dispatch_openspec_review",
                return_value=('{"result": "{}"}', 1.0),
            ),
            patch(
                "action_harness.pipeline.parse_review_result",
                return_value=_approved_review_result(),
            ),
            patch(
                "action_harness.pipeline.push_archive_if_needed",
                return_value=(False, None),
            ),
        ):
            _pr_result, manifest = run_pipeline("test-change", test_repo, max_retries=1)

        # Worker cost: 0.10, Review costs: 3 * 0.02 = 0.06
        assert manifest.total_cost_usd is not None
        assert abs(manifest.total_cost_usd - 0.16) < 0.001
