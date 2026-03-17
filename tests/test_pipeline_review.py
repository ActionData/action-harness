"""Integration tests for the review agents pipeline stage."""

import json
import subprocess
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from helpers import cleanup_worktrees

from action_harness.models import (
    EvalResult,
    OpenSpecReviewResult,
    ReviewResult,
    WorkerResult,
)
from action_harness.openspec_reviewer import parse_review_result
from action_harness.pipeline import run_pipeline
from action_harness.review_agents import format_review_feedback


def _needs_human_review_result() -> OpenSpecReviewResult:
    review_json = {
        "status": "needs-human",
        "tasks_total": 10,
        "tasks_complete": 7,
        "human_tasks_remaining": 3,
        "validation_passed": True,
        "semantic_review_passed": True,
        "findings": ["3 human tasks remaining: verify API tokens, watch CI run, merge to master"],
        "archived": False,
    }
    raw = json.dumps({"result": json.dumps(review_json)})
    return parse_review_result(raw, 1.0)


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


def _low_only_review_results() -> list[ReviewResult]:
    """Three ReviewResults with only low-severity findings."""
    from action_harness.models import ReviewFinding

    finding = ReviewFinding(
        title="Minor nit",
        file="src/baz.py",
        severity="low",
        description="Trailing whitespace",
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
def test_repo(tmp_path: Path) -> Generator[Path]:
    """Create a temporary git repo for testing.

    Cleans up any worktrees created in /tmp/action-harness-* after the test.
    """
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

    yield repo

    cleanup_worktrees(repo)


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

    def test_full_cycle_with_persistent_findings(self, test_repo: Path) -> None:
        """After all review-cycle rounds with persistent findings, post comment and continue."""
        mock = _make_claude_mock(commits=True)

        # Review agents always return findings (never clean) — including
        # the verification review that runs after the loop.
        # Default cycle is ["low", "med", "high"] = 3 rounds
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

        # Should have: initial worker + 3 fix-retry workers = 4 worker dispatches
        # (3 rounds in default cycle: low, med, high)
        worker_stages = [s for s in manifest.stages if isinstance(s, WorkerResult)]
        assert len(worker_stages) == 4  # initial + 3 fix-retries

        # 4 review dispatches: 3 rounds + verification review = 12 review stages
        review_stages = [s for s in manifest.stages if isinstance(s, ReviewResult)]
        assert len(review_stages) == 12  # 3 agents * 4 review dispatches

        # Verify a "Remaining findings" comment was posted with specific content
        gh_calls = [
            call
            for call in mock_subprocess.call_args_list
            if call[0][0][0] == "gh" and "comment" in call[0][0]
        ]
        remaining_calls = [
            call
            for call in gh_calls
            if "Remaining findings after" in call[0][0][call[0][0].index("--body") + 1]
        ]
        assert len(remaining_calls) >= 1
        body = remaining_calls[0][0][0][remaining_calls[0][0][0].index("--body") + 1]
        assert "fix-retry round(s)" in body
        assert "Off-by-one error" in body
        assert "bug-hunter" in body

    def test_fix_retry_failure_breaks_loop(self, test_repo: Path) -> None:
        """Fix-retry failure breaks loop; remaining findings are posted."""
        mock = _make_claude_mock(commits=True)

        # Make eval fail on the fix-retry attempt (second eval call)
        eval_call_count = {"n": 0}

        def eval_side_effect(*args: object, **kwargs: object) -> EvalResult:
            eval_call_count["n"] += 1
            if eval_call_count["n"] == 1:
                return _passing_eval()  # initial eval passes
            return EvalResult(
                success=False, stage="eval", commands_run=4, commands_passed=2, error="tests failed"
            )

        with (
            patch("action_harness.worker.subprocess.run", mock),
            patch("action_harness.pipeline.run_eval", side_effect=eval_side_effect),
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

        # Only 1 fix-retry worker dispatched (loop breaks after first failure)
        worker_stages = [s for s in manifest.stages if isinstance(s, WorkerResult)]
        assert len(worker_stages) == 2  # initial + 1 failed fix-retry

        # Only 1 review round (loop breaks before round 2)
        review_stages = [s for s in manifest.stages if isinstance(s, ReviewResult)]
        assert len(review_stages) == 3  # 3 agents * 1 round

        # "Remaining findings" comment should be posted since findings remain
        gh_calls = [
            call
            for call in mock_subprocess.call_args_list
            if call[0][0][0] == "gh" and "comment" in call[0][0]
        ]
        remaining_calls = [
            call
            for call in gh_calls
            if "Remaining findings after" in call[0][0][call[0][0].index("--body") + 1]
        ]
        assert len(remaining_calls) >= 1
        body = remaining_calls[0][0][0][remaining_calls[0][0][0].index("--body") + 1]
        assert "Off-by-one error" in body

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

    def test_needs_human_pipeline(self, test_repo: Path) -> None:
        """Pipeline succeeds with needs_human=True when only human tasks remain."""
        mock = _make_claude_mock(commits=True)

        # Track gh commands to verify comment and label
        gh_calls: list[list[str]] = []

        def tracking_side_effect(
            cmd: list[str], **kwargs: object
        ) -> MagicMock | subprocess.CompletedProcess[str]:
            if cmd[0] == "gh":
                gh_calls.append(cmd)
            return mock.side_effect(cmd, **kwargs)

        tracking_mock = MagicMock(side_effect=tracking_side_effect)

        with (
            patch("action_harness.worker.subprocess.run", mock),
            patch("action_harness.pipeline.run_eval", return_value=_passing_eval()),
            patch("action_harness.pr.subprocess.run", mock),
            patch("action_harness.pipeline.subprocess.run", tracking_mock),
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
                return_value=_needs_human_review_result(),
            ),
            patch(
                "action_harness.pipeline.push_archive_if_needed",
                return_value=(False, None),
            ),
        ):
            pr_result, manifest = run_pipeline("test-change", test_repo, max_retries=1)

        # Pipeline reports success
        assert pr_result.success is True

        # Manifest has needs_human flag
        assert manifest.needs_human is True

        # Verify PR comment was posted with human tasks
        comment_calls = [c for c in gh_calls if "comment" in c]
        assert len(comment_calls) >= 1
        comment_body = comment_calls[-1][comment_calls[-1].index("--body") + 1]
        assert "Human Tasks Remaining" in comment_body

        # Verify needs-human label was added
        label_calls = [c for c in gh_calls if "--add-label" in c and "needs-human" in c]
        assert len(label_calls) >= 1

    def test_short_circuit_on_low_findings_at_med_tolerance(self, test_repo: Path) -> None:
        """Low-only findings at 'med' tolerance → short-circuit, no fix-retry."""
        mock = _make_claude_mock(commits=True)

        with (
            patch("action_harness.worker.subprocess.run", mock),
            patch("action_harness.pipeline.run_eval", return_value=_passing_eval()),
            patch("action_harness.pr.subprocess.run", mock),
            patch("action_harness.pipeline.subprocess.run", mock),
            patch(
                "action_harness.pipeline.dispatch_review_agents",
                return_value=_low_only_review_results(),
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
            pr_result, manifest = run_pipeline(
                "test-change", test_repo, max_retries=1, review_cycle=["med", "high"]
            )

        assert pr_result.success is True

        # No fix-retry should have happened — only 1 initial worker dispatch
        worker_stages = [s for s in manifest.stages if isinstance(s, WorkerResult)]
        assert len(worker_stages) == 1  # initial only, no fix-retry

        # Only 1 review round (short-circuited after first round found no actionable)
        review_stages = [s for s in manifest.stages if isinstance(s, ReviewResult)]
        assert len(review_stages) == 3  # 3 agents * 1 round


class TestMaxFindingsPerRetryPipeline:
    """Task 4.2: verify max_findings_per_retry threading through pipeline."""

    def test_custom_max_findings_threaded_to_format(self, test_repo: Path) -> None:
        """Pipeline with max_findings_per_retry=2 threads to format."""
        mock = _make_claude_mock(commits=True)

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
            patch(
                "action_harness.pipeline.format_review_feedback",
                wraps=format_review_feedback,
            ) as mock_format,
        ):
            pr_result, manifest = run_pipeline(
                "test-change", test_repo, max_retries=1, max_findings_per_retry=2
            )

        assert pr_result.success is True
        # format_review_feedback should have been called with max_findings=2
        assert mock_format.call_count >= 1
        call_kwargs = mock_format.call_args[1]
        assert call_kwargs["max_findings"] == 2

    def test_default_max_findings_is_5(self, test_repo: Path) -> None:
        """Pipeline without explicit flag uses max_findings=5."""
        mock = _make_claude_mock(commits=True)

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
            patch(
                "action_harness.pipeline.format_review_feedback",
                wraps=format_review_feedback,
            ) as mock_format,
        ):
            pr_result, manifest = run_pipeline("test-change", test_repo, max_retries=1)

        assert pr_result.success is True
        assert mock_format.call_count >= 1
        call_kwargs = mock_format.call_args[1]
        assert call_kwargs["max_findings"] == 5

    def test_pr_comment_contains_all_findings(self, test_repo: Path) -> None:
        """PR comment still contains all findings (not capped)."""
        mock = _make_claude_mock(commits=True)

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
            pr_result, manifest = run_pipeline(
                "test-change", test_repo, max_retries=1, max_findings_per_retry=1
            )

        assert pr_result.success is True

        # Find gh pr comment calls — the review comment should include ALL findings
        gh_calls = [
            call
            for call in mock_subprocess.call_args_list
            if len(call[0][0]) > 2 and call[0][0][0] == "gh" and "comment" in call[0][0]
        ]
        # At least one comment should contain the finding title (unfiltered)
        comment_bodies = []
        for call in gh_calls:
            cmd = call[0][0]
            if "--body" in cmd:
                body_idx = cmd.index("--body") + 1
                comment_bodies.append(cmd[body_idx])
        assert comment_bodies, "Expected at least one gh pr comment with --body"
        assert any("Off-by-one error" in body for body in comment_bodies)


class TestFlagPrNeedsHuman:
    """Unit tests for _flag_pr_needs_human."""

    def test_posts_comment_and_adds_label(self, tmp_path: Path) -> None:
        """Verify gh pr comment and gh pr edit --add-label are called correctly."""
        from action_harness.pipeline import _flag_pr_needs_human

        calls: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch("action_harness.pipeline.subprocess.run", side_effect=fake_run):
            _flag_pr_needs_human(
                tmp_path,
                "https://github.com/test/repo/pull/1",
                ["3 human tasks remaining: verify tokens, watch CI, merge"],
                verbose=False,
            )

        # Should have exactly 2 calls: comment + label
        assert len(calls) == 2

        # First call: gh pr comment
        comment_cmd = calls[0]
        assert comment_cmd[0] == "gh"
        assert comment_cmd[1] == "pr"
        assert comment_cmd[2] == "comment"
        assert "https://github.com/test/repo/pull/1" in comment_cmd
        body_idx = comment_cmd.index("--body") + 1
        body = comment_cmd[body_idx]
        assert "Human Tasks Remaining" in body
        assert "human tasks remaining" in body

        # Second call: gh pr edit --add-label
        label_cmd = calls[1]
        assert label_cmd[0] == "gh"
        assert label_cmd[1] == "pr"
        assert label_cmd[2] == "edit"
        assert "--add-label" in label_cmd
        assert "needs-human" in label_cmd


class TestPipelineChangeNamePassedToReviewAgents:
    """Verify change_name is threaded to dispatch_review_agents."""

    def test_change_name_passed_in_change_mode(self, test_repo: Path) -> None:
        """When pipeline runs with a change name, dispatch_review_agents receives it."""
        mock = _make_claude_mock(commits=True)
        dispatch_kwargs: list[dict[str, object]] = []

        def tracking_dispatch(**kwargs: object) -> list[ReviewResult]:
            dispatch_kwargs.append(kwargs)
            return _no_findings_review_results()

        with (
            patch("action_harness.worker.subprocess.run", mock),
            patch("action_harness.pipeline.run_eval", return_value=_passing_eval()),
            patch("action_harness.pr.subprocess.run", mock),
            patch("action_harness.pipeline.subprocess.run", mock),
            patch(
                "action_harness.pipeline.dispatch_review_agents",
                side_effect=tracking_dispatch,
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
            run_pipeline("my-change", test_repo, max_retries=1)

        assert len(dispatch_kwargs) >= 1
        # Every call to dispatch_review_agents should pass change_name="my-change"
        for kw in dispatch_kwargs:
            assert kw.get("change_name") == "my-change"

    def test_prompt_mode_passes_change_name(self, test_repo: Path) -> None:
        """In prompt mode, change_name is still threaded through (no tasks.md will exist).

        This test verifies the pipeline threads change_name correctly.
        Agent-exclusion logic (spec-compliance-reviewer not dispatched when
        tasks.md is absent) is tested in test_review_agents.py —
        test_change_name_nonexistent_no_tasks_md_dispatches_three.
        """
        mock = _make_claude_mock(commits=True)
        dispatch_kwargs: list[dict[str, object]] = []

        def tracking_dispatch(**kwargs: object) -> list[ReviewResult]:
            dispatch_kwargs.append(kwargs)
            return _no_findings_review_results()

        with (
            patch("action_harness.worker.subprocess.run", mock),
            patch("action_harness.pipeline.run_eval", return_value=_passing_eval()),
            patch("action_harness.pr.subprocess.run", mock),
            patch("action_harness.pipeline.subprocess.run", mock),
            patch(
                "action_harness.pipeline.dispatch_review_agents",
                side_effect=tracking_dispatch,
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
            # CLI would pass "prompt-fix-bug" as change_name in prompt mode.
            # The pipeline threads it through regardless — dispatch_review_agents
            # will skip spec-compliance-reviewer because no tasks.md exists.
            run_pipeline(
                "prompt-fix-bug",
                test_repo,
                max_retries=1,
                prompt="fix the bug",
            )

        assert len(dispatch_kwargs) >= 1
        for kw in dispatch_kwargs:
            assert kw.get("change_name") == "prompt-fix-bug"

    def test_filters_non_human_findings(self, tmp_path: Path) -> None:
        """Only findings containing 'human' are included in the PR comment."""
        from action_harness.pipeline import _flag_pr_needs_human

        calls: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        findings = [
            "2 human tasks remaining: verify tokens, watch CI",
            "Minor style issue in foo.py",
        ]

        with patch("action_harness.pipeline.subprocess.run", side_effect=fake_run):
            _flag_pr_needs_human(
                tmp_path,
                "https://github.com/test/repo/pull/1",
                findings,
                verbose=False,
            )

        comment_cmd = calls[0]
        body_idx = comment_cmd.index("--body") + 1
        body = comment_cmd[body_idx]
        assert "human tasks remaining" in body
        assert "style issue" not in body

    def test_fallback_message_when_no_human_findings(self, tmp_path: Path) -> None:
        """When no findings contain 'human', a fallback message is shown."""
        from action_harness.pipeline import _flag_pr_needs_human

        calls: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with patch("action_harness.pipeline.subprocess.run", side_effect=fake_run):
            _flag_pr_needs_human(
                tmp_path,
                "https://github.com/test/repo/pull/1",
                ["Some unrelated finding"],
                verbose=False,
            )

        comment_cmd = calls[0]
        body_idx = comment_cmd.index("--body") + 1
        body = comment_cmd[body_idx]
        assert "Check tasks.md for details" in body
