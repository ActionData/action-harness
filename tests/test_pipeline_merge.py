"""Integration tests for the auto-merge pipeline stage."""

import json
import subprocess
from collections.abc import Generator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from action_harness.models import (
    EvalResult,
    MergeResult,
    OpenSpecReviewResult,
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


@pytest.fixture
def test_repo(tmp_path: Path) -> Path:
    """Create a temporary git repo with an OpenSpec change."""
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
    (repo / "src").mkdir()

    change_dir = repo / "openspec" / "changes" / "test-change"
    change_dir.mkdir(parents=True)
    (change_dir / "tasks.md").write_text("- [ ] 1.1 Add a feature\n")

    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        capture_output=True,
        check=True,
    )

    return repo


def _make_claude_mock(commits: bool = True) -> MagicMock:
    """Mock subprocess.run for claude and gh commands."""
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
            result.stdout = json.dumps({"cost_usd": 0.10, "result": "implemented"})
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


def _standard_patches(
    mock: MagicMock, review: OpenSpecReviewResult | None = None
) -> AbstractContextManager[None]:
    """Return a context manager of patches for the standard pipeline stages."""

    @contextmanager
    def patched() -> Generator[None]:
        with (
            patch("action_harness.worker.subprocess.run", mock),
            patch("action_harness.pipeline.run_eval", return_value=_passing_eval()),
            patch("action_harness.pr.subprocess.run", mock),
            patch(
                "action_harness.pipeline.dispatch_openspec_review",
                return_value=('{"result": "{}"}', 1.0),
            ),
            patch(
                "action_harness.pipeline.parse_review_result",
                return_value=review or _approved_review_result(),
            ),
            patch(
                "action_harness.pipeline.push_archive_if_needed",
                return_value=(False, None),
            ),
        ):
            yield

    return patched()


class TestAutoMerge:
    def test_all_gates_pass_merged(self, test_repo: Path) -> None:
        """auto-merge enabled + all gates pass → MergeResult(merged=True)."""
        mock = _make_claude_mock()

        with (
            _standard_patches(mock),
            patch("action_harness.pipeline.merge_pr") as mock_merge,
        ):
            mock_merge.return_value = MergeResult(success=True, merged=True)
            pr_result, manifest = run_pipeline(
                "test-change",
                test_repo,
                max_retries=1,
                skip_review=True,
                auto_merge=True,
            )

        assert pr_result.success is True
        merge_stages = [s for s in manifest.stages if isinstance(s, MergeResult)]
        assert len(merge_stages) == 1
        assert merge_stages[0].merged is True
        mock_merge.assert_called_once()

    def test_protected_files_blocks(self, test_repo: Path) -> None:
        """auto-merge + protected files → blocked + comment posted."""
        mock = _make_claude_mock()

        with (
            _standard_patches(mock),
            patch(
                "action_harness.pipeline.load_protected_patterns",
                return_value=["CLAUDE.md"],
            ),
            patch(
                "action_harness.pipeline.get_changed_files",
                return_value=["CLAUDE.md", "new_feature.py"],
            ),
            patch("action_harness.pipeline.post_merge_blocked_comment") as mock_comment,
        ):
            pr_result, manifest = run_pipeline(
                "test-change",
                test_repo,
                max_retries=1,
                skip_review=True,
                auto_merge=True,
            )

        merge_stages = [s for s in manifest.stages if isinstance(s, MergeResult)]
        assert len(merge_stages) == 1
        assert merge_stages[0].merged is False
        assert merge_stages[0].merge_blocked_reason is not None
        assert "no_protected_files" in merge_stages[0].merge_blocked_reason
        mock_comment.assert_called_once()

    def test_findings_remain_blocks(self, test_repo: Path) -> None:
        """auto-merge + findings remain → blocked."""
        mock = _make_claude_mock()
        from action_harness.models import ReviewFinding, ReviewResult

        finding = ReviewFinding(
            title="Bug",
            file="foo.py",
            severity="high",
            description="issue",
            agent="bug-hunter",
        )
        review_results = [
            ReviewResult(success=True, agent_name="bug-hunter", findings=[finding]),
        ]

        with (
            patch("action_harness.worker.subprocess.run", mock),
            patch("action_harness.pipeline.run_eval", return_value=_passing_eval()),
            patch("action_harness.pr.subprocess.run", mock),
            patch(
                "action_harness.pipeline.dispatch_review_agents",
                return_value=review_results,
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
            patch("action_harness.pipeline.format_review_feedback", return_value="fix these"),
            patch("action_harness.pipeline.post_merge_blocked_comment") as mock_comment,
        ):
            pr_result, manifest = run_pipeline(
                "test-change",
                test_repo,
                max_retries=1,
                skip_review=False,
                auto_merge=True,
            )

        merge_stages = [s for s in manifest.stages if isinstance(s, MergeResult)]
        assert len(merge_stages) == 1
        assert merge_stages[0].merged is False
        assert "review_clean" in (merge_stages[0].merge_blocked_reason or "")
        mock_comment.assert_called_once()

    def test_auto_merge_disabled_no_merge_result(self, test_repo: Path) -> None:
        """auto-merge disabled → no MergeResult in stages."""
        mock = _make_claude_mock()

        with _standard_patches(mock):
            pr_result, manifest = run_pipeline(
                "test-change",
                test_repo,
                max_retries=1,
                skip_review=True,
                auto_merge=False,
            )

        merge_stages = [s for s in manifest.stages if isinstance(s, MergeResult)]
        assert len(merge_stages) == 0

    def test_wait_for_ci_pass_merged(self, test_repo: Path) -> None:
        """auto-merge + wait_for_ci pass → merged with ci_passed=True from pipeline."""
        mock = _make_claude_mock()

        with (
            _standard_patches(mock),
            patch("action_harness.pipeline.merge_pr") as mock_merge,
            patch("action_harness.pipeline.wait_for_ci_checks", return_value=True),
        ):
            # Return MergeResult without ci_passed — pipeline's model_copy must set it
            mock_merge.return_value = MergeResult(success=True, merged=True)
            assert mock_merge.return_value.ci_passed is None  # confirm mock doesn't pre-set
            pr_result, manifest = run_pipeline(
                "test-change",
                test_repo,
                max_retries=1,
                skip_review=True,
                auto_merge=True,
                wait_for_ci=True,
            )

        merge_stages = [s for s in manifest.stages if isinstance(s, MergeResult)]
        assert len(merge_stages) == 1
        assert merge_stages[0].merged is True
        # ci_passed=True must come from pipeline's model_copy, not from mock
        assert merge_stages[0].ci_passed is True

    def test_wait_for_ci_fail_blocked(self, test_repo: Path) -> None:
        """auto-merge + CI fail → blocked + comment posted."""
        mock = _make_claude_mock()

        with (
            _standard_patches(mock),
            patch("action_harness.pipeline.wait_for_ci_checks", return_value=False),
            patch("action_harness.pipeline.post_merge_blocked_comment") as mock_comment,
        ):
            pr_result, manifest = run_pipeline(
                "test-change",
                test_repo,
                max_retries=1,
                skip_review=True,
                auto_merge=True,
                wait_for_ci=True,
            )

        merge_stages = [s for s in manifest.stages if isinstance(s, MergeResult)]
        assert len(merge_stages) == 1
        assert merge_stages[0].merged is False
        assert merge_stages[0].ci_passed is False
        assert "CI" in (merge_stages[0].merge_blocked_reason or "")
        mock_comment.assert_called_once()
        # Verify the gates dict passed to comment includes ci_passed=False
        comment_gates = mock_comment.call_args[0][2]
        assert comment_gates["ci_passed"] is False

    def test_skip_review_no_openspec_review_gates_pass(self, test_repo: Path) -> None:
        """auto-merge + skip_review + prompt mode (no openspec review) → gates pass."""
        mock = _make_claude_mock()

        with (
            _standard_patches(mock),
            patch("action_harness.pipeline.merge_pr") as mock_merge,
        ):
            mock_merge.return_value = MergeResult(success=True, merged=True)
            pr_result, manifest = run_pipeline(
                "test-change",
                test_repo,
                max_retries=1,
                skip_review=True,
                auto_merge=True,
            )

        merge_stages = [s for s in manifest.stages if isinstance(s, MergeResult)]
        assert len(merge_stages) == 1
        assert merge_stages[0].merged is True

    def test_openspec_review_fails_no_merge_result(self, test_repo: Path) -> None:
        """auto-merge + openspec review fails → early return, no MergeResult."""
        mock = _make_claude_mock()
        failed_review = parse_review_result(
            json.dumps(
                {
                    "result": json.dumps(
                        {
                            "status": "findings",
                            "tasks_total": 1,
                            "tasks_complete": 0,
                            "validation_passed": False,
                            "semantic_review_passed": False,
                            "findings": ["Task incomplete"],
                            "archived": False,
                        }
                    )
                }
            ),
            1.0,
        )

        with _standard_patches(mock, review=failed_review):
            pr_result, manifest = run_pipeline(
                "test-change",
                test_repo,
                max_retries=1,
                skip_review=True,
                auto_merge=True,
            )

        # Pipeline fails due to openspec review, no MergeResult
        assert pr_result.success is False
        merge_stages = [s for s in manifest.stages if isinstance(s, MergeResult)]
        assert len(merge_stages) == 0

    def test_merge_pr_command_fails(self, test_repo: Path) -> None:
        """auto-merge + gh pr merge fails → MergeResult(success=False) in stages."""
        mock = _make_claude_mock()

        with (
            _standard_patches(mock),
            patch("action_harness.pipeline.merge_pr") as mock_merge,
        ):
            mock_merge.return_value = MergeResult(
                success=False,
                merged=False,
                error="merge conflict",
            )
            pr_result, manifest = run_pipeline(
                "test-change",
                test_repo,
                max_retries=1,
                skip_review=True,
                auto_merge=True,
            )

        # Pipeline still succeeds (merge is advisory)
        assert pr_result.success is True
        merge_stages = [s for s in manifest.stages if isinstance(s, MergeResult)]
        assert len(merge_stages) == 1
        assert merge_stages[0].success is False
        assert merge_stages[0].merged is False
        assert merge_stages[0].error == "merge conflict"

    def test_auto_merge_no_pr_url_appends_blocked_result(self, test_repo: Path) -> None:
        """auto-merge enabled but pr_url is None → MergeResult(merged=False) appended."""
        mock = _make_claude_mock()

        from action_harness.models import PrResult

        # PR creation "succeeds" but without a URL
        no_url_pr = PrResult(success=True, stage="pr", branch="harness/test-change")
        assert no_url_pr.pr_url is None

        with (
            patch("action_harness.worker.subprocess.run", mock),
            patch("action_harness.pipeline.run_eval", return_value=_passing_eval()),
            patch("action_harness.pipeline.create_pr", return_value=no_url_pr),
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
            pr_result, manifest = run_pipeline(
                "test-change",
                test_repo,
                max_retries=1,
                skip_review=True,
                auto_merge=True,
            )

        merge_stages = [s for s in manifest.stages if isinstance(s, MergeResult)]
        assert len(merge_stages) == 1
        assert merge_stages[0].merged is False
        assert merge_stages[0].merge_blocked_reason == "no PR URL"
