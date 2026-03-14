"""Tests for the protection module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from action_harness.protection import (
    check_protected_files,
    flag_pr_protected,
    get_changed_files,
    load_protected_patterns,
)


class TestLoadProtectedPatterns:
    def test_file_exists_with_patterns(self, tmp_path: Path) -> None:
        harness_dir = tmp_path / ".harness"
        harness_dir.mkdir()
        config = harness_dir / "protected-paths.yml"
        config.write_text('protected:\n  - "src/pipeline.py"\n  - "CLAUDE.md"\n')

        patterns = load_protected_patterns(tmp_path)
        assert patterns == ["src/pipeline.py", "CLAUDE.md"]

    def test_file_missing_returns_empty(self, tmp_path: Path) -> None:
        patterns = load_protected_patterns(tmp_path)
        assert patterns == []

    def test_malformed_yaml_returns_empty(self, tmp_path: Path) -> None:
        harness_dir = tmp_path / ".harness"
        harness_dir.mkdir()
        config = harness_dir / "protected-paths.yml"
        config.write_text(": :\n  bad: [yaml: content\n")

        patterns = load_protected_patterns(tmp_path)
        assert patterns == []

    def test_missing_protected_key_returns_empty(self, tmp_path: Path) -> None:
        harness_dir = tmp_path / ".harness"
        harness_dir.mkdir()
        config = harness_dir / "protected-paths.yml"
        config.write_text("other_key:\n  - foo\n")

        patterns = load_protected_patterns(tmp_path)
        assert patterns == []

    def test_protected_not_a_list_returns_empty(self, tmp_path: Path) -> None:
        harness_dir = tmp_path / ".harness"
        harness_dir.mkdir()
        config = harness_dir / "protected-paths.yml"
        config.write_text("protected: not-a-list\n")

        patterns = load_protected_patterns(tmp_path)
        assert patterns == []


class TestCheckProtectedFiles:
    def test_exact_match(self) -> None:
        changed = ["src/pipeline.py", "src/worker.py"]
        patterns = ["src/pipeline.py"]
        result = check_protected_files(changed, patterns)
        assert result == ["src/pipeline.py"]

    def test_glob_match(self) -> None:
        changed = ["src/action_harness/worker.py", "README.md"]
        patterns = ["src/action_harness/*.py"]
        result = check_protected_files(changed, patterns)
        assert result == ["src/action_harness/worker.py"]

    def test_no_match_returns_empty(self) -> None:
        changed = ["src/new_module.py", "tests/test_new.py"]
        patterns = ["src/pipeline.py", "CLAUDE.md"]
        result = check_protected_files(changed, patterns)
        assert result == []

    def test_multiple_matches(self) -> None:
        changed = ["src/pipeline.py", "CLAUDE.md", "tests/test_new.py"]
        patterns = ["src/pipeline.py", "CLAUDE.md"]
        result = check_protected_files(changed, patterns)
        assert result == ["src/pipeline.py", "CLAUDE.md"]

    def test_empty_patterns(self) -> None:
        changed = ["src/pipeline.py"]
        result = check_protected_files(changed, [])
        assert result == []

    def test_empty_changed_files(self) -> None:
        patterns = ["src/pipeline.py"]
        result = check_protected_files([], patterns)
        assert result == []


class TestGetChangedFiles:
    def test_returns_file_list(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "src/pipeline.py\nCLAUDE.md\n"

        with patch(
            "action_harness.protection.subprocess.run", return_value=mock_result
        ) as mock_run:
            files = get_changed_files(Path("/tmp/worktree"), "main")

        assert files == ["src/pipeline.py", "CLAUDE.md"]
        mock_run.assert_called_once_with(
            ["git", "diff", "--name-only", "origin/main..HEAD"],
            cwd=Path("/tmp/worktree"),
            capture_output=True,
            text=True,
        )

    def test_failure_returns_empty(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "fatal: bad revision"

        with patch("action_harness.protection.subprocess.run", return_value=mock_result):
            files = get_changed_files(Path("/tmp/worktree"), "main")

        assert files == []

    def test_exception_returns_empty(self) -> None:
        with patch(
            "action_harness.protection.subprocess.run",
            side_effect=FileNotFoundError("git not found"),
        ):
            files = get_changed_files(Path("/tmp/worktree"), "main")

        assert files == []

    def test_empty_output_returns_empty(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""

        with patch("action_harness.protection.subprocess.run", return_value=mock_result):
            files = get_changed_files(Path("/tmp/worktree"), "main")

        assert files == []


class TestFlagPrProtected:
    def test_posts_comment_and_adds_label(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch(
            "action_harness.protection.subprocess.run", return_value=mock_result
        ) as mock_run:
            flag_pr_protected(
                "https://github.com/org/repo/pull/1",
                ["src/pipeline.py", "CLAUDE.md"],
                Path("/tmp/worktree"),
                verbose=False,
            )

        assert mock_run.call_count == 2

        # First call: gh pr comment
        comment_call = mock_run.call_args_list[0]
        cmd = comment_call[0][0]
        assert cmd[0] == "gh"
        assert cmd[1] == "pr"
        assert cmd[2] == "comment"
        assert "https://github.com/org/repo/pull/1" in cmd

        # Second call: gh pr edit --add-label
        label_call = mock_run.call_args_list[1]
        cmd = label_call[0][0]
        assert cmd[0] == "gh"
        assert cmd[1] == "pr"
        assert cmd[2] == "edit"
        assert "--add-label" in cmd
        assert "protected-paths" in cmd

    def test_empty_list_does_nothing(self) -> None:
        with patch("action_harness.protection.subprocess.run") as mock_run:
            flag_pr_protected(
                "https://github.com/org/repo/pull/1",
                [],
                Path("/tmp/worktree"),
                verbose=False,
            )

        mock_run.assert_not_called()

    def test_comment_failure_is_non_fatal(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "gh error"

        with patch("action_harness.protection.subprocess.run", return_value=mock_result):
            # Should not raise
            flag_pr_protected(
                "https://github.com/org/repo/pull/1",
                ["src/pipeline.py"],
                Path("/tmp/worktree"),
                verbose=False,
            )

    def test_exception_is_non_fatal(self) -> None:
        with patch(
            "action_harness.protection.subprocess.run",
            side_effect=FileNotFoundError("gh not found"),
        ):
            # Should not raise
            flag_pr_protected(
                "https://github.com/org/repo/pull/1",
                ["src/pipeline.py"],
                Path("/tmp/worktree"),
                verbose=False,
            )
