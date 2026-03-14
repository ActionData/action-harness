"""Integration tests for the full pipeline. Uses a real git repo with mocked Claude CLI."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from action_harness.models import EvalResult, OpenSpecReviewResult, RunManifest
from action_harness.openspec_reviewer import parse_review_result
from action_harness.pipeline import run_pipeline

# ruff: noqa: E501


def _approved_review_result() -> OpenSpecReviewResult:
    """Return a pre-built approved OpenSpecReviewResult for mocking."""
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
    """Create a temporary git repo with pyproject.toml, a test, and an OpenSpec change."""
    repo = tmp_path / "repo"
    repo.mkdir()

    # Initialize git repo
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

    # Create pyproject.toml
    (repo / "pyproject.toml").write_text('[project]\nname = "test"\nversion = "0.1.0"\n')

    # Create a passing test
    (repo / "tests").mkdir()
    (repo / "tests" / "__init__.py").write_text("")
    (repo / "tests" / "test_basic.py").write_text("def test_ok() -> None:\n    assert True\n")

    # Create an OpenSpec change directory
    change_dir = repo / "openspec" / "changes" / "test-change"
    change_dir.mkdir(parents=True)
    (change_dir / "tasks.md").write_text("- [ ] 1.1 Add a feature\n")

    # Create src directory
    (repo / "src").mkdir()

    # Initial commit
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
    returncode: int = 0,
    cost: float = 0.10,
) -> MagicMock:
    """Create a mock for subprocess.run that simulates the claude CLI.

    When commits=True, the mock creates a file and commits it in the worktree
    before returning (simulating a worker that produces work).
    """
    original_run = subprocess.run

    def side_effect(
        cmd: list[str], **kwargs: object
    ) -> MagicMock | subprocess.CompletedProcess[str]:
        if cmd[0] == "claude":
            # Simulate the worker producing a commit
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
            result.returncode = returncode
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
            # Simulate successful push
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result
        else:
            # Pass through to real git for worktree operations, rev-list, etc.
            return original_run(cmd, **kwargs)

    mock = MagicMock(side_effect=side_effect)
    return mock


class TestPipelineSuccess:
    def _passing_eval(self) -> EvalResult:
        return EvalResult(success=True, stage="eval", commands_run=4, commands_passed=4)

    def _mock_review(self) -> OpenSpecReviewResult:
        return _approved_review_result()

    def test_full_pipeline_happy_path(self, test_repo: Path) -> None:
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
                return_value=self._mock_review(),
            ),
            patch(
                "action_harness.pipeline.push_archive_if_needed",
                return_value=(False, None),
            ),
        ):
            pr_result, manifest = run_pipeline(
                "test-change", test_repo, max_retries=1, skip_review=True
            )

        assert pr_result.success is True
        assert pr_result.pr_url == "https://github.com/test/repo/pull/1"
        assert pr_result.branch == "harness/test-change"

        assert manifest.success is True
        assert manifest.change_name == "test-change"
        assert manifest.retries == 0
        assert manifest.pr_url == "https://github.com/test/repo/pull/1"
        assert manifest.error is None

    def test_pipeline_creates_worktree(self, test_repo: Path) -> None:
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
                return_value=self._mock_review(),
            ),
            patch(
                "action_harness.pipeline.push_archive_if_needed",
                return_value=(False, None),
            ),
        ):
            _pr_result, _manifest = run_pipeline("test-change", test_repo, skip_review=True)

        # Verify branch was created
        check = subprocess.run(
            ["git", "rev-parse", "--verify", "harness/test-change"],
            cwd=test_repo,
            capture_output=True,
            text=True,
        )
        assert check.returncode == 0

    def test_worker_invoked_with_correct_args(self, test_repo: Path) -> None:
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
                return_value=self._mock_review(),
            ),
            patch(
                "action_harness.pipeline.push_archive_if_needed",
                return_value=(False, None),
            ),
        ):
            _pr_result, _manifest = run_pipeline(
                "test-change", test_repo, max_turns=50, skip_review=True
            )

        # Find claude invocation
        claude_calls = [c for c in mock.call_args_list if c[0][0][0] == "claude"]
        assert len(claude_calls) >= 1
        cmd = claude_calls[0][0][0]
        assert "--system-prompt" in cmd
        assert "--max-turns" in cmd
        idx = cmd.index("--max-turns")
        assert cmd[idx + 1] == "50"

    def test_worker_config_threaded_through_pipeline(self, test_repo: Path) -> None:
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
                return_value=self._mock_review(),
            ),
            patch(
                "action_harness.pipeline.push_archive_if_needed",
                return_value=(False, None),
            ),
        ):
            _pr_result, _manifest = run_pipeline(
                "test-change",
                test_repo,
                model="opus",
                effort="high",
                max_budget_usd=2.0,
                permission_mode="plan",
                skip_review=True,
            )

        claude_calls = [c for c in mock.call_args_list if c[0][0][0] == "claude"]
        assert len(claude_calls) >= 1
        cmd = claude_calls[0][0][0]
        idx = cmd.index("--model")
        assert cmd[idx + 1] == "opus"
        idx = cmd.index("--effort")
        assert cmd[idx + 1] == "high"
        idx = cmd.index("--max-budget-usd")
        assert cmd[idx + 1] == "2.0"
        idx = cmd.index("--permission-mode")
        assert cmd[idx + 1] == "plan"


class TestPipelineFailure:
    def test_worker_no_commits_retries_then_fails(self, test_repo: Path) -> None:
        mock = _make_claude_mock(commits=False)

        with patch("action_harness.worker.subprocess.run", mock):
            pr_result, manifest = run_pipeline("test-change", test_repo, max_retries=2)

        assert pr_result.success is False
        assert "No commits" in (pr_result.error or "")

        assert manifest.success is False
        assert manifest.retries == 2
        assert manifest.error is not None

    def test_max_retries_respected(self, test_repo: Path) -> None:
        mock = _make_claude_mock(commits=False)

        with patch("action_harness.worker.subprocess.run", mock):
            _pr_result, _manifest = run_pipeline("test-change", test_repo, max_retries=2)

        # Count claude invocations — should be max_retries + 1 (initial + retries)
        claude_calls = [c for c in mock.call_args_list if c[0][0][0] == "claude"]
        assert len(claude_calls) == 3  # 1 initial + 2 retries

    def test_eval_failure_then_retry_succeeds(self, test_repo: Path) -> None:
        """Eval fails on first attempt, retry succeeds."""
        mock = _make_claude_mock(commits=True)
        fail_eval = EvalResult(
            success=False,
            stage="eval",
            error="Eval failed: uv run pytest -v",
            commands_run=1,
            commands_passed=0,
            failed_command="uv run pytest -v",
            feedback_prompt="## Eval Failure\n\n### Command: uv run pytest -v\n...",
        )
        pass_eval = EvalResult(success=True, stage="eval", commands_run=4, commands_passed=4)

        with (
            patch("action_harness.worker.subprocess.run", mock),
            patch("action_harness.pipeline.run_eval", side_effect=[fail_eval, pass_eval]),
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
                "test-change", test_repo, max_retries=3, skip_review=True
            )

        assert pr_result.success is True
        assert pr_result.pr_url is not None

        # Verify worker was called twice (initial + retry)
        claude_calls = [c for c in mock.call_args_list if c[0][0][0] == "claude"]
        assert len(claude_calls) == 2

        # Verify the second call includes feedback in the user prompt
        second_prompt = claude_calls[1][0][0][2]  # cmd[2] is the -p argument
        assert "Eval Failure" in second_prompt

        # Manifest should record 1 retry
        assert manifest.retries == 1
        assert manifest.success is True

    def test_worktree_failure_returns_error(self, tmp_path: Path) -> None:
        """Pipeline fails gracefully when worktree creation fails."""
        # tmp_path has git init but no commits — worktree add will fail
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        change_dir = tmp_path / "openspec" / "changes" / "test-change"
        change_dir.mkdir(parents=True)

        pr_result, manifest = run_pipeline("test-change", tmp_path)

        assert pr_result.success is False
        assert pr_result.error is not None

        assert manifest.success is False
        assert manifest.error is not None
        assert len(manifest.stages) == 1  # Only worktree stage

    def test_worktree_cleaned_up_on_failure(self, test_repo: Path) -> None:
        mock = _make_claude_mock(commits=False)

        with patch("action_harness.worker.subprocess.run", mock):
            pr_result, _manifest = run_pipeline("test-change", test_repo, max_retries=0)

        assert pr_result.success is False

        # Worktree should be cleaned up (no lingering worktrees)
        list_result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=test_repo,
            capture_output=True,
            text=True,
        )
        worktrees = [
            line
            for line in list_result.stdout.splitlines()
            if line.startswith("worktree ") and "harness" in line
        ]
        assert len(worktrees) == 0


class TestManifestPersistence:
    def _passing_eval(self) -> EvalResult:
        return EvalResult(success=True, stage="eval", commands_run=4, commands_passed=4)

    def test_manifest_written_to_disk_on_success(self, test_repo: Path) -> None:
        mock = _make_claude_mock(commits=True, cost=0.25)

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
            _pr_result, manifest = run_pipeline(
                "test-change", test_repo, max_retries=1, skip_review=True
            )

        # Manifest path should be set
        assert manifest.manifest_path is not None
        manifest_file = Path(manifest.manifest_path)
        assert manifest_file.exists()

        # Verify the directory structure
        runs_dir = test_repo / ".action-harness" / "runs"
        assert runs_dir.exists()

        # Verify the JSON deserializes to a valid RunManifest
        raw = manifest_file.read_text()
        restored = RunManifest.model_validate_json(raw)
        assert restored.change_name == "test-change"
        assert restored.success is True
        assert restored.total_cost_usd == 0.25

    def test_manifest_written_to_disk_on_failure(self, test_repo: Path) -> None:
        mock = _make_claude_mock(commits=False)

        with patch("action_harness.worker.subprocess.run", mock):
            _pr_result, manifest = run_pipeline("test-change", test_repo, max_retries=1)

        assert manifest.manifest_path is not None
        manifest_file = Path(manifest.manifest_path)
        assert manifest_file.exists()

        restored = RunManifest.model_validate_json(manifest_file.read_text())
        assert restored.success is False
        assert restored.error is not None
        assert restored.retries == 1

    def test_manifest_filename_contains_change_name(self, test_repo: Path) -> None:
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
            _pr_result, manifest = run_pipeline(
                "test-change", test_repo, max_retries=1, skip_review=True
            )

        assert manifest.manifest_path is not None
        assert "test-change.json" in manifest.manifest_path

    def test_manifest_cost_sums_all_worker_results(self, test_repo: Path) -> None:
        """Cost should sum across all worker dispatches including retries."""
        mock = _make_claude_mock(commits=True, cost=0.10)
        fail_eval = EvalResult(
            success=False,
            stage="eval",
            error="failed",
            commands_run=1,
            commands_passed=0,
            failed_command="uv run pytest -v",
            feedback_prompt="## Eval Failure\n...",
        )
        pass_eval = EvalResult(success=True, stage="eval", commands_run=4, commands_passed=4)

        with (
            patch("action_harness.worker.subprocess.run", mock),
            patch("action_harness.pipeline.run_eval", side_effect=[fail_eval, pass_eval]),
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
            _pr_result, manifest = run_pipeline(
                "test-change", test_repo, max_retries=3, skip_review=True
            )

        # Two worker dispatches at $0.10 each
        assert manifest.total_cost_usd is not None
        assert abs(manifest.total_cost_usd - 0.20) < 0.001


class TestPipelineWithOpenspecReview:
    def _passing_eval(self) -> EvalResult:
        return EvalResult(success=True, stage="eval", commands_run=4, commands_passed=4)

    def _approved_review_output(self) -> str:
        """Raw stdout simulating a claude CLI JSON response with approved review."""
        review_json = {
            "status": "approved",
            "tasks_total": 5,
            "tasks_complete": 5,
            "validation_passed": True,
            "semantic_review_passed": True,
            "findings": [],
            "archived": True,
        }
        return json.dumps({"result": json.dumps(review_json), "cost_usd": 0.05})

    def _findings_review_output(self) -> str:
        """Raw stdout simulating a claude CLI JSON response with findings."""
        review_json = {
            "status": "findings",
            "tasks_total": 5,
            "tasks_complete": 3,
            "validation_passed": False,
            "semantic_review_passed": False,
            "findings": ["Task 1.4 incomplete", "Validation errors found"],
            "archived": False,
        }
        return json.dumps({"result": json.dumps(review_json), "cost_usd": 0.03})

    def test_pipeline_openspec_review_approved(self, test_repo: Path) -> None:
        """Pipeline succeeds when openspec review approves."""
        mock = _make_claude_mock(commits=True)
        review_output = self._approved_review_output()

        # The review dispatch calls claude again — we need to intercept it
        original_side_effect = mock.side_effect

        call_count = {"claude": 0}

        def side_effect_with_review(
            cmd: list[str], **kwargs: object
        ) -> MagicMock | subprocess.CompletedProcess[str]:
            if cmd[0] == "claude":
                call_count["claude"] += 1
                if call_count["claude"] == 1:
                    # First claude call is the worker
                    return original_side_effect(cmd, **kwargs)
                else:
                    # Second claude call is the review agent
                    result = MagicMock()
                    result.returncode = 0
                    result.stdout = review_output
                    result.stderr = ""
                    return result
            return original_side_effect(cmd, **kwargs)

        mock_with_review = MagicMock(side_effect=side_effect_with_review)

        with (
            patch("action_harness.worker.subprocess.run", mock_with_review),
            patch("action_harness.pipeline.run_eval", return_value=self._passing_eval()),
            patch("action_harness.pr.subprocess.run", mock_with_review),
            patch("action_harness.openspec_reviewer.subprocess.run", mock_with_review),
            patch("action_harness.pipeline.subprocess.run", mock_with_review),
            patch(
                "action_harness.openspec_reviewer.count_commits_ahead",
                return_value=3,
            ),
        ):
            pr_result, manifest = run_pipeline(
                "test-change", test_repo, max_retries=1, skip_review=True
            )

        assert pr_result.success is True
        assert pr_result.pr_url == "https://github.com/test/repo/pull/1"
        assert manifest.success is True

        # Verify openspec-review stage is in the manifest
        review_stages = [s for s in manifest.stages if isinstance(s, OpenSpecReviewResult)]
        assert len(review_stages) == 1
        assert review_stages[0].success is True
        assert review_stages[0].archived is True

    def test_pipeline_openspec_review_findings(self, test_repo: Path) -> None:
        """Pipeline fails when openspec review returns findings."""
        mock = _make_claude_mock(commits=True)
        findings_output = self._findings_review_output()

        original_side_effect = mock.side_effect
        call_count = {"claude": 0}

        def side_effect_with_findings(
            cmd: list[str], **kwargs: object
        ) -> MagicMock | subprocess.CompletedProcess[str]:
            if cmd[0] == "claude":
                call_count["claude"] += 1
                if call_count["claude"] == 1:
                    return original_side_effect(cmd, **kwargs)
                else:
                    result = MagicMock()
                    result.returncode = 0
                    result.stdout = findings_output
                    result.stderr = ""
                    return result
            return original_side_effect(cmd, **kwargs)

        mock_with_findings = MagicMock(side_effect=side_effect_with_findings)

        with (
            patch("action_harness.worker.subprocess.run", mock_with_findings),
            patch("action_harness.pipeline.run_eval", return_value=self._passing_eval()),
            patch("action_harness.pr.subprocess.run", mock_with_findings),
            patch("action_harness.openspec_reviewer.subprocess.run", mock_with_findings),
            patch("action_harness.pipeline.subprocess.run", mock_with_findings),
            patch(
                "action_harness.openspec_reviewer.count_commits_ahead",
                return_value=3,
            ),
        ):
            pr_result, manifest = run_pipeline(
                "test-change", test_repo, max_retries=1, skip_review=True
            )

        assert pr_result.success is False
        assert manifest.success is False

        # Verify openspec-review stage has findings
        review_stages = [s for s in manifest.stages if isinstance(s, OpenSpecReviewResult)]
        assert len(review_stages) == 1
        assert review_stages[0].success is False
        assert len(review_stages[0].findings) == 2


class TestEventLogIntegration:
    def _passing_eval(self) -> EvalResult:
        return EvalResult(success=True, stage="eval", commands_run=4, commands_passed=4)

    def test_event_log_path_populated_and_valid(self, test_repo: Path) -> None:
        """Manifest.event_log_path is set and the file contains valid JSON-lines."""
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
            _pr_result, manifest = run_pipeline("test-change", test_repo, max_retries=1)

        # event_log_path should be set
        assert manifest.event_log_path is not None
        log_file = Path(manifest.event_log_path)
        assert log_file.exists()

        # Every line must be valid JSON with required fields
        lines = log_file.read_text().strip().splitlines()
        assert len(lines) >= 2  # at minimum: run.started + run.completed

        event_types = []
        for line in lines:
            parsed = json.loads(line)
            assert "timestamp" in parsed
            assert "event" in parsed
            assert "run_id" in parsed
            event_types.append(parsed["event"])

        # First event should be run.started, last should be run.completed
        assert event_types[0] == "run.started"
        assert event_types[-1] == "run.completed"

        # Should contain key stage events for a happy path
        assert "worktree.created" in event_types
        assert "worker.dispatched" in event_types
        assert "worker.completed" in event_types
        assert "pr.created" in event_types


class TestProtectedPathsIntegration:
    def _passing_eval(self) -> EvalResult:
        return EvalResult(success=True, stage="eval", commands_run=4, commands_passed=4)

    def test_manifest_protected_files_populated(self, test_repo: Path) -> None:
        """Protected files appear in manifest when diff touches protected paths."""
        # Create .harness/protected-paths.yml in the test repo
        harness_dir = test_repo / ".harness"
        harness_dir.mkdir()
        (harness_dir / "protected-paths.yml").write_text('protected:\n  - "new_feature.py"\n')
        subprocess.run(["git", "add", "."], cwd=test_repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "add protected paths config"],
            cwd=test_repo,
            capture_output=True,
            check=True,
        )

        mock = _make_claude_mock(commits=True)

        # Mock get_changed_files since the test repo has no origin remote
        mock_changed = MagicMock(return_value=["new_feature.py"])

        with (
            patch("action_harness.worker.subprocess.run", mock),
            patch("action_harness.pipeline.run_eval", return_value=self._passing_eval()),
            patch("action_harness.pr.subprocess.run", mock),
            patch("action_harness.pipeline.subprocess.run", mock),
            patch("action_harness.pipeline.get_changed_files", mock_changed),
            patch("action_harness.pipeline.flag_pr_protected"),
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
                "test-change", test_repo, max_retries=1, skip_review=True
            )

        assert pr_result.success is True
        # The mocked get_changed_files returns new_feature.py which matches the protected pattern
        assert "new_feature.py" in manifest.protected_files

    def test_manifest_empty_when_no_protected_config(self, test_repo: Path) -> None:
        """Without config, protected_files is empty."""
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
            pr_result, manifest = run_pipeline(
                "test-change", test_repo, max_retries=1, skip_review=True
            )

        assert pr_result.success is True
        assert manifest.protected_files == []
