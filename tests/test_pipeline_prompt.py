"""Tests for pipeline behavior in prompt mode (no OpenSpec change)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from action_harness.models import (
    OpenSpecReviewResult,
    StageResultUnion,
)
from action_harness.pipeline import run_pipeline


def _make_subprocess_mock() -> MagicMock:
    """Create a subprocess mock that handles all pipeline stages."""
    mock = MagicMock()

    def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
        result = MagicMock()
        result.returncode = 0
        result.stderr = ""

        if cmd[0] == "claude":
            result.stdout = json.dumps({"cost_usd": 0.01, "result": "ok"})
        elif cmd[0] == "git" and "rev-list" in cmd:
            result.stdout = "1\n"
        elif cmd[0] == "git" and "symbolic-ref" in cmd:
            result.stdout = "refs/remotes/origin/main\n"
        elif cmd[0] == "git" and "worktree" in cmd and "add" in cmd:
            result.stdout = ""
        elif cmd[0] == "git" and "push" in cmd:
            result.stdout = ""
        elif cmd[0] == "git" and "diff" in cmd:
            result.stdout = "file.py | 5 +++++\n"
        elif cmd[0] == "git" and "log" in cmd:
            result.stdout = "abc1234 Fix bug\n"
        elif cmd[0] == "gh" and "pr" in cmd and "create" in cmd:
            result.stdout = "https://github.com/test/repo/pull/1\n"
        elif cmd[0] == "gh" and "pr" in cmd and "comment" in cmd:
            result.stdout = ""
        else:
            result.stdout = ""
        return result

    mock.side_effect = side_effect
    return mock


def _setup_fake_repo(tmp_path: Path) -> Path:
    """Create a minimal fake repo for pipeline tests."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    return repo


class TestPipelinePromptMode:
    """Tests for pipeline behavior with prompt parameter."""

    def test_no_openspec_review_in_prompt_mode(self, tmp_path: Path) -> None:
        """When pipeline runs with prompt, no OpenSpecReviewResult should appear."""
        repo = _setup_fake_repo(tmp_path)
        mock = _make_subprocess_mock()

        with (
            patch("action_harness.pipeline.subprocess.run", mock),
            patch("action_harness.worker.subprocess.run", mock),
            patch("action_harness.evaluator.subprocess.run", mock),
            patch("action_harness.pr.subprocess.run", mock),
            patch("action_harness.worktree.subprocess.run", mock),
            patch("action_harness.protection.load_protected_patterns", return_value=[]),
        ):
            pr_result, manifest = run_pipeline(
                change_name="prompt-fix-bug",
                repo=repo,
                max_retries=0,
                max_turns=10,
                skip_review=True,
                prompt="Fix the bug",
            )

        # No OpenSpecReviewResult in stages
        openspec_stages = [
            s for s in manifest.stages if isinstance(s, OpenSpecReviewResult)
        ]
        assert len(openspec_stages) == 0

    def test_openspec_review_runs_without_prompt(self, tmp_path: Path) -> None:
        """When pipeline runs without prompt (change mode), OpenSpec review runs."""
        repo = _setup_fake_repo(tmp_path)
        # Create change dir for OpenSpec review
        change_dir = repo / "openspec" / "changes" / "my-change"
        change_dir.mkdir(parents=True)
        mock = _make_subprocess_mock()

        with (
            patch("action_harness.pipeline.subprocess.run", mock),
            patch("action_harness.worker.subprocess.run", mock),
            patch("action_harness.evaluator.subprocess.run", mock),
            patch("action_harness.pr.subprocess.run", mock),
            patch("action_harness.worktree.subprocess.run", mock),
            patch("action_harness.openspec_reviewer.subprocess.run", mock),
            patch("action_harness.protection.load_protected_patterns", return_value=[]),
        ):
            pr_result, manifest = run_pipeline(
                change_name="my-change",
                repo=repo,
                max_retries=0,
                max_turns=10,
                skip_review=True,
            )

        # Should have an OpenSpecReviewResult in stages
        openspec_stages = [
            s for s in manifest.stages if isinstance(s, OpenSpecReviewResult)
        ]
        assert len(openspec_stages) > 0
