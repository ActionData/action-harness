"""Tests for session resume in the pipeline retry loop and review fix-retry."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from action_harness.event_log import EventLogger
from action_harness.models import (
    EvalResult,
    OpenSpecReviewResult,
    PrResult,
    ReviewFinding,
    ReviewResult,
    StageResultUnion,
    WorkerResult,
    WorktreeResult,
)
from action_harness.pipeline import _run_pipeline_inner, _run_review_fix_retry


@pytest.fixture(autouse=True)
def _mock_preflight(mock_preflight: None) -> None:
    """Auto-apply shared mock_preflight fixture from conftest."""


def _make_worker_result(
    success: bool = True,
    session_id: str | None = "sess_a",
    context_usage_pct: float | None = 0.05,
    commits_ahead: int = 1,
    cost_usd: float = 0.10,
    error: str | None = None,
) -> WorkerResult:
    return WorkerResult(
        success=success,
        stage="worker",
        commits_ahead=commits_ahead,
        cost_usd=cost_usd,
        session_id=session_id,
        context_usage_pct=context_usage_pct,
        error=error,
    )


def _failing_eval(feedback: str = "## Eval Failure\nTests failed") -> EvalResult:
    return EvalResult(
        success=False,
        stage="eval",
        error="pytest failed",
        commands_run=1,
        commands_passed=0,
        failed_command="uv run pytest -v",
        feedback_prompt=feedback,
    )


def _passing_eval() -> EvalResult:
    return EvalResult(success=True, stage="eval", commands_run=4, commands_passed=4)


def _approved_review() -> OpenSpecReviewResult:
    return OpenSpecReviewResult(
        success=True,
        tasks_total=1,
        tasks_complete=1,
        validation_passed=True,
        semantic_review_passed=True,
        archived=True,
    )


@pytest.fixture
def dummy_logger(tmp_path: Path) -> EventLogger:
    return EventLogger(tmp_path / "test.events.jsonl", "test-run")


def _run_inner_with_mocks(
    mock_dispatch: MagicMock,
    mock_eval: MagicMock,
    stages: list[StageResultUnion],
    dummy_logger: EventLogger,
    max_retries: int = 3,
    mock_create_pr: MagicMock | None = None,
    mock_write_progress: MagicMock | None = None,
) -> PrResult:
    """Helper to call _run_pipeline_inner with all required mocks."""
    wt_result = WorktreeResult(success=True, worktree_path=Path("/fake/wt"), branch="harness/test")
    if not stages:
        stages.append(wt_result)

    wp_mock = mock_write_progress if mock_write_progress is not None else MagicMock()

    with (
        patch("action_harness.pipeline.dispatch_worker", side_effect=mock_dispatch),
        patch("action_harness.pipeline.run_eval", side_effect=mock_eval),
        patch("action_harness.pipeline.create_worktree", return_value=wt_result),
        patch("action_harness.pipeline.create_pr") as mock_pr,
        patch("action_harness.pipeline._get_worktree_base", return_value="main"),
        patch("action_harness.pipeline.cleanup_worktree"),
        patch(
            "action_harness.pipeline._run_openspec_review",
            return_value=_approved_review(),
        ),
        patch("action_harness.pipeline.write_progress", wp_mock),
    ):
        if mock_create_pr is not None:
            mock_pr.side_effect = mock_create_pr
        else:
            mock_pr.return_value = MagicMock(success=True, pr_url="http://pr/1", branch="b")
        return _run_pipeline_inner(
            "test-change",
            Path("/fake/repo"),
            max_retries=max_retries,
            max_turns=200,
            model=None,
            effort=None,
            max_budget_usd=None,
            permission_mode="bypassPermissions",
            verbose=False,
            stages=stages,
            logger=dummy_logger,
            skip_review=True,
        )


class TestEvalRetryWithResume:
    """Pipeline eval retry loop passes session_id when context is fresh."""

    def test_resume_when_context_below_threshold(self, dummy_logger: EventLogger) -> None:
        """When context < 60% and session_id present, next dispatch uses resume."""
        dispatch_calls: list[dict[str, str | None]] = []

        def mock_dispatch(*args: object, **kwargs: object) -> WorkerResult:
            dispatch_calls.append(
                {
                    "session_id": kwargs.get("session_id"),  # type: ignore[dict-item]
                }
            )
            if len(dispatch_calls) == 1:
                return _make_worker_result(session_id="sess_a", context_usage_pct=0.05)
            return _make_worker_result(session_id="sess_b", context_usage_pct=0.10)

        # Eval: initial fails, pre-work fails (triggers dispatch), retry passes
        eval_results = [_failing_eval(), _failing_eval(), _passing_eval()]
        eval_idx = {"i": 0}

        def mock_eval(*args: object, **kwargs: object) -> EvalResult:
            result = eval_results[eval_idx["i"]]
            eval_idx["i"] += 1
            return result

        stages: list[StageResultUnion] = []
        _run_inner_with_mocks(mock_dispatch, mock_eval, stages, dummy_logger)

        assert len(dispatch_calls) == 2
        assert dispatch_calls[0]["session_id"] is None
        assert dispatch_calls[1]["session_id"] == "sess_a"

    def test_fresh_dispatch_when_context_above_threshold(self, dummy_logger: EventLogger) -> None:
        """When context >= 60%, next dispatch is fresh (no resume)."""
        dispatch_calls: list[dict[str, str | None]] = []

        def mock_dispatch(*args: object, **kwargs: object) -> WorkerResult:
            dispatch_calls.append(
                {
                    "session_id": kwargs.get("session_id"),  # type: ignore[dict-item]
                }
            )
            if len(dispatch_calls) == 1:
                return _make_worker_result(session_id="sess_a", context_usage_pct=0.75)
            return _make_worker_result(session_id="sess_b", context_usage_pct=0.10)

        # Eval: initial fails, pre-work fails (triggers dispatch), retry passes
        eval_results = [_failing_eval(), _failing_eval(), _passing_eval()]
        eval_idx = {"i": 0}

        def mock_eval(*args: object, **kwargs: object) -> EvalResult:
            result = eval_results[eval_idx["i"]]
            eval_idx["i"] += 1
            return result

        stages: list[StageResultUnion] = []
        _run_inner_with_mocks(mock_dispatch, mock_eval, stages, dummy_logger)

        assert len(dispatch_calls) == 2
        assert dispatch_calls[0]["session_id"] is None
        assert dispatch_calls[1]["session_id"] is None

    def test_resume_fallback_on_failure(self, dummy_logger: EventLogger) -> None:
        """If resumed dispatch fails, fall back to fresh in the same iteration."""
        dispatch_calls: list[dict[str, str | None]] = []

        def mock_dispatch(*args: object, **kwargs: object) -> WorkerResult:
            sid = kwargs.get("session_id")
            dispatch_calls.append({"session_id": sid})  # type: ignore[dict-item]
            if len(dispatch_calls) == 1:
                return _make_worker_result(session_id="sess_a", context_usage_pct=0.05)
            elif len(dispatch_calls) == 2:
                return _make_worker_result(
                    success=False, session_id="sess_a", error="resume failed"
                )
            else:
                return _make_worker_result(session_id="sess_c", context_usage_pct=0.10)

        # Eval sequence: initial eval fails, pre-work eval fails, retry eval passes
        eval_results = [_failing_eval(), _failing_eval(), _passing_eval()]
        eval_idx = {"i": 0}

        def mock_eval(*args: object, **kwargs: object) -> EvalResult:
            result = eval_results[eval_idx["i"]]
            eval_idx["i"] += 1
            return result

        stages: list[StageResultUnion] = []
        _run_inner_with_mocks(mock_dispatch, mock_eval, stages, dummy_logger)

        assert len(dispatch_calls) == 3
        assert dispatch_calls[0]["session_id"] is None
        assert dispatch_calls[1]["session_id"] == "sess_a"
        assert dispatch_calls[2]["session_id"] is None

    def test_chained_resumes(self, dummy_logger: EventLogger) -> None:
        """Retry 2 uses session_id from retry 1, not from the original dispatch."""
        dispatch_calls: list[dict[str, str | None]] = []

        def mock_dispatch(*args: object, **kwargs: object) -> WorkerResult:
            dispatch_calls.append({"session_id": kwargs.get("session_id")})  # type: ignore[dict-item]
            if len(dispatch_calls) == 1:
                return _make_worker_result(session_id="sess_a", context_usage_pct=0.05)
            elif len(dispatch_calls) == 2:
                return _make_worker_result(session_id="sess_b", context_usage_pct=0.10)
            else:
                return _make_worker_result(session_id="sess_c", context_usage_pct=0.15)

        # Eval: initial fail, pre-work fail, retry1 fail, pre-work fail, retry2 pass
        eval_results = [
            _failing_eval(),
            _failing_eval(),
            _failing_eval(),
            _failing_eval(),
            _passing_eval(),
        ]
        eval_idx = {"i": 0}

        def mock_eval(*args: object, **kwargs: object) -> EvalResult:
            result = eval_results[eval_idx["i"]]
            eval_idx["i"] += 1
            return result

        stages: list[StageResultUnion] = []
        _run_inner_with_mocks(mock_dispatch, mock_eval, stages, dummy_logger)

        assert len(dispatch_calls) == 3
        assert dispatch_calls[0]["session_id"] is None
        assert dispatch_calls[1]["session_id"] == "sess_a"
        assert dispatch_calls[2]["session_id"] == "sess_b"


class TestReviewFixRetryWithResume:
    """Review fix-retry uses session_id from the last successful worker."""

    def test_fix_retry_resumes_last_successful_worker(self) -> None:
        stages: list[StageResultUnion] = [
            WorktreeResult(success=True, worktree_path=Path("/fake"), branch="b"),
            _make_worker_result(success=True, session_id="sess_abc"),
            _passing_eval(),
        ]
        review_finding = ReviewFinding(
            title="Bug",
            file="foo.py",
            severity="high",
            description="desc",
            agent="bug-hunter",
        )
        review_results = [
            ReviewResult(
                success=True,
                agent_name="bug-hunter",
                findings=[review_finding],
            )
        ]

        dispatch_calls: list[dict[str, str | None]] = []

        def mock_dispatch(*args: object, **kwargs: object) -> WorkerResult:
            dispatch_calls.append({"session_id": kwargs.get("session_id")})  # type: ignore[dict-item]
            return _make_worker_result(success=True, session_id="sess_fix")

        mock_pr = MagicMock()
        mock_pr.pr_url = "http://pr/1"

        with (
            patch("action_harness.pipeline.dispatch_worker", side_effect=mock_dispatch),
            patch("action_harness.pipeline.run_eval", return_value=_passing_eval()),
            patch("action_harness.pipeline.subprocess.run") as mock_subprocess,
            patch("action_harness.pipeline._get_worktree_base", return_value="main"),
        ):
            mock_subprocess.return_value = MagicMock(returncode=0)
            result = _run_review_fix_retry(
                "test-change",
                mock_pr,
                Path("/fake/wt"),
                Path("/fake/repo"),
                max_turns=200,
                model=None,
                effort=None,
                max_budget_usd=None,
                permission_mode="bypassPermissions",
                verbose=False,
                stages=stages,
                review_results=review_results,
            )

        assert result is True
        assert len(dispatch_calls) == 1
        assert dispatch_calls[0]["session_id"] == "sess_abc"

    def test_fix_retry_fresh_when_no_session_id(self) -> None:
        stages: list[StageResultUnion] = [
            WorktreeResult(success=True, worktree_path=Path("/fake"), branch="b"),
            _make_worker_result(success=True, session_id=None),
            _passing_eval(),
        ]
        review_finding = ReviewFinding(
            title="Bug",
            file="foo.py",
            severity="high",
            description="desc",
            agent="bug-hunter",
        )
        review_results = [
            ReviewResult(
                success=True,
                agent_name="bug-hunter",
                findings=[review_finding],
            )
        ]

        dispatch_calls: list[dict[str, str | None]] = []

        def mock_dispatch(*args: object, **kwargs: object) -> WorkerResult:
            dispatch_calls.append({"session_id": kwargs.get("session_id")})  # type: ignore[dict-item]
            return _make_worker_result(success=True)

        mock_pr = MagicMock()
        mock_pr.pr_url = "http://pr/1"

        with (
            patch("action_harness.pipeline.dispatch_worker", side_effect=mock_dispatch),
            patch("action_harness.pipeline.run_eval", return_value=_passing_eval()),
            patch("action_harness.pipeline.subprocess.run") as mock_subprocess,
            patch("action_harness.pipeline._get_worktree_base", return_value="main"),
        ):
            mock_subprocess.return_value = MagicMock(returncode=0)
            result = _run_review_fix_retry(
                "test-change",
                mock_pr,
                Path("/fake/wt"),
                Path("/fake/repo"),
                max_turns=200,
                model=None,
                effort=None,
                max_budget_usd=None,
                permission_mode="bypassPermissions",
                verbose=False,
                stages=stages,
                review_results=review_results,
            )

        assert result is True
        assert len(dispatch_calls) == 1
        assert dispatch_calls[0]["session_id"] is None

    def test_fix_retry_resume_fallback_to_fresh(self) -> None:
        """If resume fails during review fix-retry, falls back to fresh dispatch."""
        stages: list[StageResultUnion] = [
            WorktreeResult(success=True, worktree_path=Path("/fake"), branch="b"),
            _make_worker_result(success=True, session_id="sess_abc"),
            _passing_eval(),
        ]
        review_finding = ReviewFinding(
            title="Bug",
            file="foo.py",
            severity="high",
            description="desc",
            agent="bug-hunter",
        )
        review_results = [
            ReviewResult(
                success=True,
                agent_name="bug-hunter",
                findings=[review_finding],
            )
        ]

        dispatch_calls: list[dict[str, str | None]] = []

        def mock_dispatch(*args: object, **kwargs: object) -> WorkerResult:
            sid = kwargs.get("session_id")
            dispatch_calls.append({"session_id": sid})  # type: ignore[dict-item]
            if sid is not None:
                return _make_worker_result(
                    success=False, session_id="sess_abc", error="resume failed"
                )
            return _make_worker_result(success=True, session_id="sess_fresh")

        mock_pr = MagicMock()
        mock_pr.pr_url = "http://pr/1"

        with (
            patch("action_harness.pipeline.dispatch_worker", side_effect=mock_dispatch),
            patch("action_harness.pipeline.run_eval", return_value=_passing_eval()),
            patch("action_harness.pipeline.subprocess.run") as mock_subprocess,
            patch("action_harness.pipeline._get_worktree_base", return_value="main"),
        ):
            mock_subprocess.return_value = MagicMock(returncode=0)
            result = _run_review_fix_retry(
                "test-change",
                mock_pr,
                Path("/fake/wt"),
                Path("/fake/repo"),
                max_turns=200,
                model=None,
                effort=None,
                max_budget_usd=None,
                permission_mode="bypassPermissions",
                verbose=False,
                stages=stages,
                review_results=review_results,
            )

        assert result is True
        assert len(dispatch_calls) == 2
        assert dispatch_calls[0]["session_id"] == "sess_abc"
        assert dispatch_calls[1]["session_id"] is None


class TestPreWorkEval:
    """Pre-work eval runs before retry when prior worker produced commits."""

    def test_pre_work_eval_passes_skips_retry(self, dummy_logger: EventLogger) -> None:
        """When pre-work eval passes, worker is NOT dispatched for the retry.

        create_pr receives the prior worker_result and the pre-work eval_result.
        """
        dispatch_calls: list[dict[str, str | None]] = []

        def mock_dispatch(*args: object, **kwargs: object) -> WorkerResult:
            dispatch_calls.append({"session_id": kwargs.get("session_id")})  # type: ignore[dict-item]
            return _make_worker_result(session_id="sess_a", context_usage_pct=0.05, commits_ahead=3)

        # Eval sequence: first eval fails (triggers retry), pre-work eval passes
        eval_results = [_failing_eval(), _passing_eval()]
        eval_idx = {"i": 0}

        def mock_eval(*args: object, **kwargs: object) -> EvalResult:
            result = eval_results[eval_idx["i"]]
            eval_idx["i"] += 1
            return result

        create_pr_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

        def mock_create_pr(*args: object, **kwargs: object) -> MagicMock:
            create_pr_calls.append((args, kwargs))
            return MagicMock(success=True, pr_url="http://pr/1", branch="b")

        stages: list[StageResultUnion] = []
        _run_inner_with_mocks(
            mock_dispatch, mock_eval, stages, dummy_logger, mock_create_pr=mock_create_pr
        )

        # Only 1 worker dispatch (no retry worker)
        assert len(dispatch_calls) == 1
        # 2 eval calls: initial eval (fail) + pre-work eval (pass)
        assert eval_idx["i"] == 2

        # create_pr received the prior worker_result and pre-work eval_result
        assert len(create_pr_calls) == 1
        pr_args = create_pr_calls[0][0]
        pr_kwargs = create_pr_calls[0][1]
        # eval_result arg (positional): should be the passing pre-work eval
        eval_arg = pr_args[3]  # create_pr(change, wt, branch, eval_result, ...)
        assert isinstance(eval_arg, EvalResult)
        assert eval_arg.success is True
        # worker_result kwarg: should be the original worker (marked successful)
        worker_arg = pr_kwargs.get("worker_result")
        assert isinstance(worker_arg, WorkerResult)
        assert worker_arg.commits_ahead == 3
        assert worker_arg.success is True

    def test_pre_work_eval_fails_dispatches_with_fresh_feedback(
        self, dummy_logger: EventLogger
    ) -> None:
        """When pre-work eval fails, worker IS dispatched with fresh feedback."""
        dispatch_calls: list[dict[str, object]] = []

        def mock_dispatch(*args: object, **kwargs: object) -> WorkerResult:
            dispatch_calls.append({"feedback": kwargs.get("feedback")})
            return _make_worker_result(session_id="sess_a", context_usage_pct=0.05, commits_ahead=2)

        # Eval sequence: first eval fails, pre-work eval fails with fresh error, second eval passes
        fresh_eval_failure = _failing_eval(feedback="mypy error")
        eval_results = [_failing_eval(feedback="stale error"), fresh_eval_failure, _passing_eval()]
        eval_idx = {"i": 0}

        def mock_eval(*args: object, **kwargs: object) -> EvalResult:
            result = eval_results[eval_idx["i"]]
            eval_idx["i"] += 1
            return result

        stages: list[StageResultUnion] = []
        _run_inner_with_mocks(mock_dispatch, mock_eval, stages, dummy_logger)

        assert len(dispatch_calls) == 2
        # Second dispatch should have the fresh feedback from pre-work eval, not stale
        assert dispatch_calls[1]["feedback"] == "mypy error"

    def test_pre_work_eval_not_run_after_zero_commits(self, dummy_logger: EventLogger) -> None:
        """When prior worker produced zero commits, pre-work eval is NOT run.

        Also verifies write_progress is NOT called on the worker-failure path.
        """
        dispatch_calls: list[dict[str, object]] = []

        def mock_dispatch(*args: object, **kwargs: object) -> WorkerResult:
            dispatch_calls.append({"feedback": kwargs.get("feedback")})
            if len(dispatch_calls) == 1:
                # First dispatch fails with zero commits
                return _make_worker_result(
                    success=False, commits_ahead=0, error="No commits", session_id=None
                )
            # Second dispatch succeeds
            return _make_worker_result(session_id="sess_b", commits_ahead=1)

        # Only one eval call needed (after the second successful dispatch)
        eval_results = [_passing_eval()]
        eval_idx = {"i": 0}

        def mock_eval(*args: object, **kwargs: object) -> EvalResult:
            result = eval_results[eval_idx["i"]]
            eval_idx["i"] += 1
            return result

        wp_mock = MagicMock()
        stages: list[StageResultUnion] = []
        _run_inner_with_mocks(
            mock_dispatch, mock_eval, stages, dummy_logger, mock_write_progress=wp_mock
        )

        # 2 worker dispatches (initial fail + retry)
        assert len(dispatch_calls) == 2
        # Only 1 eval call — no pre-work eval was run
        assert eval_idx["i"] == 1
        # write_progress NOT called on worker-failure path (no eval ran)
        wp_mock.assert_not_called()


class TestRetryProgressIntegration:
    """2-retry scenario: progress file, prompt injection, and pre-work eval."""

    def test_two_retry_scenario(self, tmp_path: Path, dummy_logger: EventLogger) -> None:
        """Full 2-retry scenario with progress file verification."""
        from action_harness.progress import PROGRESS_FILENAME

        worktree = tmp_path / "wt"
        worktree.mkdir()

        dispatch_calls: list[dict[str, object]] = []

        def mock_dispatch(*args: object, **kwargs: object) -> WorkerResult:
            dispatch_calls.append({"feedback": kwargs.get("feedback")})
            return _make_worker_result(
                session_id=f"sess_{len(dispatch_calls)}", context_usage_pct=0.05, commits_ahead=2
            )

        # Eval sequence:
        # 1. Initial eval fails
        # 2. Pre-work eval for retry 1 fails
        # 3. Retry 1 eval fails
        # 4. Pre-work eval for retry 2 fails
        # 5. Retry 2 eval passes
        eval_results = [
            _failing_eval("error 1"),
            _failing_eval("pre-work error 1"),
            _failing_eval("error 2"),
            _failing_eval("pre-work error 2"),
            _passing_eval(),
        ]
        eval_idx = {"i": 0}

        def mock_eval(*args: object, **kwargs: object) -> EvalResult:
            result = eval_results[eval_idx["i"]]
            eval_idx["i"] += 1
            return result

        wt_result = WorktreeResult(success=True, worktree_path=worktree, branch="harness/test")
        stages: list[StageResultUnion] = []

        with (
            patch("action_harness.pipeline.dispatch_worker", side_effect=mock_dispatch),
            patch("action_harness.pipeline.run_eval", side_effect=mock_eval),
            patch("action_harness.pipeline.create_worktree", return_value=wt_result),
            patch("action_harness.pipeline.create_pr") as mock_pr,
            patch("action_harness.pipeline._get_worktree_base", return_value="main"),
            patch("action_harness.pipeline.cleanup_worktree"),
            patch(
                "action_harness.pipeline._run_openspec_review",
                return_value=_approved_review(),
            ),
        ):
            mock_pr.return_value = MagicMock(success=True, pr_url="http://pr/1", branch="b")
            result = _run_pipeline_inner(
                "test-change",
                Path("/fake/repo"),
                max_retries=3,
                max_turns=200,
                model=None,
                effort=None,
                max_budget_usd=None,
                permission_mode="bypassPermissions",
                verbose=False,
                stages=stages,
                logger=dummy_logger,
                skip_review=True,
            )

        assert result.success is True

        # 3 worker dispatches (initial + 2 retries)
        assert len(dispatch_calls) == 3

        # Progress file should have 2 attempt sections (written after eval fails for retries 1 & 2)
        progress_file = worktree / PROGRESS_FILENAME
        assert progress_file.exists()
        content = progress_file.read_text()
        assert "## Attempt 1" in content
        assert "## Attempt 2" in content

        # Retry workers should get pre-work eval feedback (not stale feedback)
        assert dispatch_calls[1]["feedback"] == "pre-work error 1"
        assert dispatch_calls[2]["feedback"] == "pre-work error 2"

        # Pre-work eval was called before each retry dispatch
        assert eval_idx["i"] == 5  # all 5 eval calls consumed
