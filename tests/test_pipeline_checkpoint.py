"""Tests for pipeline checkpoint integration and resume logic."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from action_harness.checkpoint import find_latest_checkpoint, write_checkpoint
from action_harness.models import (
    EvalResult,
    OpenSpecReviewResult,
    PipelineCheckpoint,
    WorkerResult,
    WorktreeResult,
)
from action_harness.pipeline import _should_run_stage, run_pipeline


def _approved_review_result() -> OpenSpecReviewResult:
    from action_harness.openspec_reviewer import parse_review_result

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


@pytest.fixture
def test_repo(tmp_path: Path) -> Path:
    """Create a temporary git repo with pyproject.toml and an OpenSpec change."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True, timeout=120)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo,
        capture_output=True,
        check=True,
        timeout=120,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        capture_output=True,
        check=True,
        timeout=120,
    )
    (repo / "pyproject.toml").write_text('[project]\nname = "test"\nversion = "0.1.0"\n')
    (repo / "tests").mkdir()
    (repo / "tests" / "__init__.py").write_text("")
    (repo / "tests" / "test_basic.py").write_text("def test_ok() -> None:\n    assert True\n")
    change_dir = repo / "openspec" / "changes" / "test-change"
    change_dir.mkdir(parents=True)
    (change_dir / "tasks.md").write_text("- [ ] 1.1 Add a feature\n")
    (repo / "src").mkdir()
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True, timeout=120)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        capture_output=True,
        check=True,
        timeout=120,
    )
    return repo


def _make_claude_mock(
    commits: bool = True,
    cost: float = 0.10,
) -> MagicMock:
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

    mock = MagicMock(side_effect=side_effect)
    return mock


class TestShouldRunStage:
    def test_no_checkpoint_runs_all(self) -> None:
        assert _should_run_stage("worktree", None) is True
        assert _should_run_stage("worker_eval", None) is True
        assert _should_run_stage("pr", None) is True
        assert _should_run_stage("review", None) is True
        assert _should_run_stage("openspec_review", None) is True

    def test_skips_completed_stages(self) -> None:
        cp = PipelineCheckpoint(
            run_id="run-1",
            change_name="test",
            repo_path="/tmp/r",
            completed_stage="pr",
            timestamp="2026-01-01T00:00:00+00:00",
        )
        assert _should_run_stage("worktree", cp) is False
        assert _should_run_stage("worker_eval", cp) is False
        assert _should_run_stage("pr", cp) is False
        assert _should_run_stage("review", cp) is True
        assert _should_run_stage("openspec_review", cp) is True

    def test_completed_worktree_skips_only_worktree(self) -> None:
        cp = PipelineCheckpoint(
            run_id="run-1",
            change_name="test",
            repo_path="/tmp/r",
            completed_stage="worktree",
            timestamp="2026-01-01T00:00:00+00:00",
        )
        assert _should_run_stage("worktree", cp) is False
        assert _should_run_stage("worker_eval", cp) is True

    def test_unknown_stage_runs(self) -> None:
        cp = PipelineCheckpoint(
            run_id="run-1",
            change_name="test",
            repo_path="/tmp/r",
            completed_stage="pr",
            timestamp="2026-01-01T00:00:00+00:00",
        )
        assert _should_run_stage("unknown_stage", cp) is True


class TestCheckpointWriteDuringPipeline:
    def _passing_eval(self) -> EvalResult:
        return EvalResult(success=True, stage="eval", commands_run=4, commands_passed=4)

    def test_successful_pipeline_deletes_checkpoint(self, test_repo: Path) -> None:
        mock = _make_claude_mock(commits=True)

        with (
            patch("action_harness.worker.subprocess.run", mock),
            patch("action_harness.pipeline.run_eval", return_value=self._passing_eval()),
            patch("action_harness.pr.subprocess.run", mock),
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
            pr_result, _manifest = run_pipeline(
                "test-change", test_repo, max_retries=1, skip_review=True
            )

        assert pr_result.success is True

        # Checkpoint should be cleaned up on success
        checkpoints_dir = test_repo / ".action-harness" / "checkpoints"
        if checkpoints_dir.exists():
            checkpoint_files = list(checkpoints_dir.glob("*.json"))
            assert len(checkpoint_files) == 0, (
                f"Expected no checkpoint files after success, found: {checkpoint_files}"
            )

    def test_failed_pipeline_preserves_checkpoint(self, test_repo: Path) -> None:
        mock = _make_claude_mock(commits=False)

        with patch("action_harness.worker.subprocess.run", mock):
            pr_result, _manifest = run_pipeline("test-change", test_repo, max_retries=0)

        assert pr_result.success is False

        # Checkpoint should exist (worktree checkpoint at minimum)
        checkpoints_dir = test_repo / ".action-harness" / "checkpoints"
        if checkpoints_dir.exists():
            checkpoint_files = list(checkpoints_dir.glob("*.json"))
            assert len(checkpoint_files) >= 1

    def test_checkpoint_written_at_each_stage(self, test_repo: Path) -> None:
        mock = _make_claude_mock(commits=True)
        stages_written: list[str] = []
        original_write = write_checkpoint

        def tracking_write(repo_path: Path, cp: PipelineCheckpoint) -> None:
            stages_written.append(cp.completed_stage)
            original_write(repo_path, cp)

        with (
            patch("action_harness.worker.subprocess.run", mock),
            patch("action_harness.pipeline.run_eval", return_value=self._passing_eval()),
            patch("action_harness.pr.subprocess.run", mock),
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
            patch("action_harness.pipeline.write_checkpoint", tracking_write),
        ):
            pr_result, _manifest = run_pipeline(
                "test-change", test_repo, max_retries=1, skip_review=True
            )

        assert pr_result.success is True
        assert "worktree" in stages_written
        assert "worker_eval" in stages_written
        assert "pr" in stages_written
        assert "review" in stages_written
        assert "openspec_review" in stages_written


class TestResumeLogic:
    def _passing_eval(self) -> EvalResult:
        return EvalResult(success=True, stage="eval", commands_run=4, commands_passed=4)

    def _make_pr_stage_checkpoint(
        self,
        test_repo: Path,
        worktree_path: Path,
        branch: str = "harness/test-change",
    ) -> PipelineCheckpoint:
        """Create a checkpoint that has completed through PR stage."""
        worker = WorkerResult(
            success=True,
            stage="worker",
            commits_ahead=2,
            cost_usd=0.10,
            session_id="sess_abc",
        )
        eval_res = EvalResult(
            success=True,
            stage="eval",
            commands_run=4,
            commands_passed=4,
        )
        wt = WorktreeResult(
            success=True,
            stage="worktree",
            worktree_path=worktree_path,
            branch=branch,
        )

        # Get actual HEAD SHA from the worktree
        head_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        head_sha = head_result.stdout.strip() if head_result.returncode == 0 else None

        return PipelineCheckpoint(
            run_id="resumed-run-id",
            change_name="test-change",
            repo_path=str(test_repo.resolve()),
            completed_stage="pr",
            worktree_path=str(worktree_path),
            branch=branch,
            branch_head_sha=head_sha,
            pr_url="https://github.com/test/repo/pull/99",
            session_id="sess_abc",
            last_worker_result=worker,
            last_eval_result=eval_res,
            protected_files=[],
            stages=[wt, worker, eval_res],
            timestamp="2026-01-01T00:00:00+00:00",
            ecosystem="python",
            skip_review=True,
        )

    def test_resume_skips_completed_stages(self, test_repo: Path) -> None:
        """Resume with completed_stage='pr' should skip worktree, worker_eval, and pr."""
        mock = _make_claude_mock(commits=True)

        # Create a real worktree so the checkpoint is valid
        wt_result = subprocess.run(
            ["git", "worktree", "add", "-b", "harness/test-change", str(test_repo / "wt")],
            cwd=test_repo,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert wt_result.returncode == 0
        worktree_path = test_repo / "wt"

        checkpoint = self._make_pr_stage_checkpoint(test_repo, worktree_path)

        # Track which stages actually run
        create_worktree_called = False

        original_create_worktree = __import__(
            "action_harness.worktree", fromlist=["create_worktree"]
        ).create_worktree

        def track_create_worktree(*args: object, **kwargs: object) -> object:
            nonlocal create_worktree_called
            create_worktree_called = True
            return original_create_worktree(*args, **kwargs)

        with (
            patch("action_harness.pipeline.create_worktree", track_create_worktree),
            patch("action_harness.worker.subprocess.run", mock),
            patch("action_harness.pipeline.run_eval", return_value=self._passing_eval()),
            patch("action_harness.pr.subprocess.run", mock),
            patch("action_harness.pipeline.create_pr") as mock_create_pr,
            patch("action_harness.pipeline.dispatch_worker") as mock_dispatch,
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
                "test-change",
                test_repo,
                max_retries=1,
                skip_review=True,
                checkpoint=checkpoint,
            )

        # Worktree, worker, eval, and PR stages should have been SKIPPED
        assert not create_worktree_called
        assert not mock_dispatch.called
        assert not mock_create_pr.called

        # PR result should use checkpoint's PR URL
        assert pr_result.success is True

        # Manifest should contain stages from checkpoint
        assert len(manifest.stages) >= 3  # at least worktree + worker + eval from checkpoint

    def test_resume_with_missing_worktree_starts_fresh(self, test_repo: Path) -> None:
        """If the worktree path no longer exists, start fresh."""
        mock = _make_claude_mock(commits=True)
        checkpoint = PipelineCheckpoint(
            run_id="old-run",
            change_name="test-change",
            repo_path=str(test_repo.resolve()),
            completed_stage="pr",
            worktree_path="/tmp/nonexistent-worktree-12345",
            branch="harness/test-change",
            timestamp="2026-01-01T00:00:00+00:00",
        )

        with (
            patch("action_harness.worker.subprocess.run", mock),
            patch("action_harness.pipeline.run_eval", return_value=self._passing_eval()),
            patch("action_harness.pr.subprocess.run", mock),
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
            pr_result, _manifest = run_pipeline(
                "test-change",
                test_repo,
                max_retries=1,
                skip_review=True,
                checkpoint=checkpoint,
            )

        # Should succeed — started fresh
        assert pr_result.success is True

    def test_resume_with_mismatched_change_name_starts_fresh(self, test_repo: Path) -> None:
        mock = _make_claude_mock(commits=True)
        checkpoint = PipelineCheckpoint(
            run_id="old-run",
            change_name="different-change",
            repo_path=str(test_repo.resolve()),
            completed_stage="pr",
            worktree_path="/tmp/wt",
            branch="harness/different-change",
            timestamp="2026-01-01T00:00:00+00:00",
        )

        with (
            patch("action_harness.worker.subprocess.run", mock),
            patch("action_harness.pipeline.run_eval", return_value=self._passing_eval()),
            patch("action_harness.pr.subprocess.run", mock),
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
            pr_result, _manifest = run_pipeline(
                "test-change",
                test_repo,
                max_retries=1,
                skip_review=True,
                checkpoint=checkpoint,
            )

        assert pr_result.success is True

    def test_resume_with_different_head_starts_fresh(self, test_repo: Path) -> None:
        """If the branch HEAD SHA doesn't match, start fresh."""
        mock = _make_claude_mock(commits=True)

        # Create real worktree
        wt_result = subprocess.run(
            ["git", "worktree", "add", "-b", "harness/test-change", str(test_repo / "wt")],
            cwd=test_repo,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert wt_result.returncode == 0

        checkpoint = PipelineCheckpoint(
            run_id="old-run",
            change_name="test-change",
            repo_path=str(test_repo.resolve()),
            completed_stage="pr",
            worktree_path=str(test_repo / "wt"),
            branch="harness/test-change",
            branch_head_sha="deadbeef00000000",  # wrong SHA
            timestamp="2026-01-01T00:00:00+00:00",
        )

        with (
            patch("action_harness.worker.subprocess.run", mock),
            patch("action_harness.pipeline.run_eval", return_value=self._passing_eval()),
            patch("action_harness.pr.subprocess.run", mock),
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
            pr_result, _manifest = run_pipeline(
                "test-change",
                test_repo,
                max_retries=1,
                skip_review=True,
                checkpoint=checkpoint,
            )

        # Should have started fresh (mismatched HEAD)
        assert pr_result.success is True

    def test_resume_latest_finds_most_recent(self, test_repo: Path) -> None:
        """find_latest_checkpoint returns the checkpoint with the latest timestamp."""
        cp1 = PipelineCheckpoint(
            run_id="run-old",
            change_name="test-change",
            repo_path=str(test_repo),
            completed_stage="worktree",
            timestamp="2026-01-01T00:00:00+00:00",
        )
        cp2 = PipelineCheckpoint(
            run_id="run-new",
            change_name="test-change",
            repo_path=str(test_repo),
            completed_stage="pr",
            timestamp="2026-01-01T02:00:00+00:00",
        )
        write_checkpoint(test_repo, cp1)
        write_checkpoint(test_repo, cp2)

        latest = find_latest_checkpoint(test_repo, "test-change")
        assert latest is not None
        assert latest.run_id == "run-new"

    def test_resume_with_no_checkpoint_starts_fresh(self, test_repo: Path) -> None:
        mock = _make_claude_mock(commits=True)

        with (
            patch("action_harness.worker.subprocess.run", mock),
            patch("action_harness.pipeline.run_eval", return_value=self._passing_eval()),
            patch("action_harness.pr.subprocess.run", mock),
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
            # Pass None checkpoint — should start fresh without error
            pr_result, _manifest = run_pipeline(
                "test-change",
                test_repo,
                max_retries=1,
                skip_review=True,
                checkpoint=None,
            )

        assert pr_result.success is True

    def test_resume_at_worker_eval_skips_to_pr(self, test_repo: Path) -> None:
        """Resume with completed_stage='worker_eval' should skip worktree+worker_eval,
        then create_pr receives worker_result and eval_result from checkpoint."""
        mock = _make_claude_mock(commits=True)

        # Create a real worktree so the checkpoint is valid
        wt_result = subprocess.run(
            ["git", "worktree", "add", "-b", "harness/test-change", str(test_repo / "wt")],
            cwd=test_repo,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert wt_result.returncode == 0
        worktree_path = test_repo / "wt"

        # Create a file + commit so there's something for the PR
        (worktree_path / "feature.py").write_text("# feature\n")
        subprocess.run(
            ["git", "add", "."],
            cwd=worktree_path,
            capture_output=True,
            check=True,
            timeout=120,
        )
        subprocess.run(
            ["git", "commit", "-m", "Add feature"],
            cwd=worktree_path,
            capture_output=True,
            check=True,
            timeout=120,
        )

        # Get actual HEAD SHA
        head_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=worktree_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        head_sha = head_result.stdout.strip()

        worker = WorkerResult(
            success=True,
            stage="worker",
            commits_ahead=1,
            cost_usd=0.10,
            session_id="sess_from_checkpoint",
        )
        eval_res = EvalResult(
            success=True,
            stage="eval",
            commands_run=4,
            commands_passed=4,
        )
        wt = WorktreeResult(
            success=True,
            stage="worktree",
            worktree_path=worktree_path,
            branch="harness/test-change",
        )

        checkpoint = PipelineCheckpoint(
            run_id="resumed-worker-eval",
            change_name="test-change",
            repo_path=str(test_repo.resolve()),
            completed_stage="worker_eval",
            worktree_path=str(worktree_path),
            branch="harness/test-change",
            branch_head_sha=head_sha,
            session_id="sess_from_checkpoint",
            last_worker_result=worker,
            last_eval_result=eval_res,
            protected_files=[],
            stages=[wt, worker, eval_res],
            timestamp="2026-01-01T00:00:00+00:00",
            ecosystem="python",
            skip_review=True,
        )

        with (
            patch("action_harness.pipeline.create_worktree") as mock_create_wt,
            patch("action_harness.pipeline.dispatch_worker") as mock_dispatch,
            patch("action_harness.pr.subprocess.run", mock),
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
            patch("action_harness.pipeline.create_pr") as mock_create_pr,
        ):
            from action_harness.models import PrResult

            mock_create_pr.return_value = PrResult(
                success=True,
                stage="pr",
                pr_url="https://github.com/test/repo/pull/42",
                branch="harness/test-change",
            )

            pr_result, manifest = run_pipeline(
                "test-change",
                test_repo,
                max_retries=1,
                skip_review=True,
                checkpoint=checkpoint,
            )

        # Worktree and worker stages should have been SKIPPED
        assert not mock_create_wt.called
        assert not mock_dispatch.called

        # create_pr SHOULD have been called (pr stage runs after worker_eval)
        assert mock_create_pr.called
        call_args = mock_create_pr.call_args
        # Positional arg 3 (index 3) is eval_result
        assert call_args[0][3] == eval_res
        # worker_result is passed as kwarg
        assert call_args[1]["worker_result"] == worker

        assert pr_result.success is True
