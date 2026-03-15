"""Tests for progress file writing."""

from pathlib import Path

from action_harness.models import EvalResult, WorkerResult
from action_harness.progress import PROGRESS_FILENAME, write_progress


def _make_worker_result(
    commits_ahead: int = 3,
    cost_usd: float = 0.23,
    duration_seconds: float = 45.2,
) -> WorkerResult:
    return WorkerResult(
        success=True,
        stage="worker",
        commits_ahead=commits_ahead,
        cost_usd=cost_usd,
        duration_seconds=duration_seconds,
    )


def _make_eval_result(
    success: bool = False,
    feedback_prompt: str = "ruff: unused import",
) -> EvalResult:
    return EvalResult(
        success=success,
        stage="eval",
        commands_run=1,
        commands_passed=0 if not success else 1,
        feedback_prompt=feedback_prompt if not success else None,
    )


class TestWriteProgress:
    def test_first_call_creates_file_with_header_and_attempt(self, tmp_path: Path) -> None:
        worker = _make_worker_result()
        eval_r = _make_eval_result(success=False, feedback_prompt="ruff: unused import")

        write_progress(tmp_path, 1, worker, eval_r)

        progress = tmp_path / PROGRESS_FILENAME
        assert progress.exists()
        content = progress.read_text()
        assert "# Harness Progress" in content
        assert "## Attempt 1" in content
        assert str(worker.commits_ahead) in content
        assert str(worker.cost_usd) in content
        assert str(worker.duration_seconds) in content
        assert "ruff: unused import" in content
        assert "FAILED" in content

    def test_second_call_appends_without_overwriting(self, tmp_path: Path) -> None:
        worker1 = _make_worker_result(commits_ahead=3, cost_usd=0.23, duration_seconds=45.2)
        eval1 = _make_eval_result(success=False, feedback_prompt="ruff error")

        worker2 = _make_worker_result(commits_ahead=1, cost_usd=0.11, duration_seconds=22.1)
        eval2 = _make_eval_result(success=False, feedback_prompt="mypy error")

        write_progress(tmp_path, 1, worker1, eval1)
        write_progress(tmp_path, 2, worker2, eval2)

        content = (tmp_path / PROGRESS_FILENAME).read_text()
        assert "## Attempt 1" in content
        assert "## Attempt 2" in content
        assert "ruff error" in content
        assert "mypy error" in content

    def test_gitignore_created_when_missing(self, tmp_path: Path) -> None:
        worker = _make_worker_result()
        eval_r = _make_eval_result()

        write_progress(tmp_path, 1, worker, eval_r)

        gitignore = tmp_path / ".gitignore"
        assert gitignore.exists()
        assert PROGRESS_FILENAME in gitignore.read_text()

    def test_gitignore_appended_when_exists(self, tmp_path: Path) -> None:
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("*.pyc\n")

        worker = _make_worker_result()
        eval_r = _make_eval_result()

        write_progress(tmp_path, 1, worker, eval_r)

        content = gitignore.read_text()
        assert "*.pyc" in content
        assert PROGRESS_FILENAME in content

    def test_gitignore_idempotent(self, tmp_path: Path) -> None:
        worker = _make_worker_result()
        eval_r = _make_eval_result()

        write_progress(tmp_path, 1, worker, eval_r)
        write_progress(tmp_path, 2, worker, eval_r)

        content = (tmp_path / ".gitignore").read_text()
        assert content.count(PROGRESS_FILENAME) == 1

    def test_passed_eval_written(self, tmp_path: Path) -> None:
        worker = _make_worker_result()
        eval_r = _make_eval_result(success=True)

        write_progress(tmp_path, 1, worker, eval_r)

        content = (tmp_path / PROGRESS_FILENAME).read_text()
        assert "PASSED" in content
        # No feedback line when eval passes
        assert "**Feedback**" not in content
