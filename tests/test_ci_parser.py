"""Tests for CI workflow parsing."""

from pathlib import Path

from action_harness.ci_parser import parse_github_actions


def _create_workflow(tmp_path: Path, filename: str, content: str) -> None:
    """Create a workflow file in the standard location."""
    workflows_dir = tmp_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)
    (workflows_dir / filename).write_text(content)


def test_full_checks_workflow(tmp_path: Path) -> None:
    """Workflow with all checks reports all signals as true."""
    _create_workflow(
        tmp_path,
        "ci.yml",
        """
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: uv run pytest -v
      - run: uv run ruff check .
      - run: uv run mypy src/
      - run: uv run ruff format --check .
""",
    )
    signals = parse_github_actions(tmp_path)
    assert signals.ci_exists is True
    assert signals.triggers_on_pr is True
    assert signals.runs_tests is True
    assert signals.runs_lint is True
    assert signals.runs_typecheck is True
    assert signals.runs_format_check is True


def test_tests_only_workflow(tmp_path: Path) -> None:
    """Workflow with only test step reports only runs_tests."""
    _create_workflow(
        tmp_path,
        "ci.yml",
        """
name: CI
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: npm test
""",
    )
    signals = parse_github_actions(tmp_path)
    assert signals.ci_exists is True
    assert signals.triggers_on_pr is False
    assert signals.runs_tests is True
    assert signals.runs_lint is False


def test_pr_trigger_dict_form(tmp_path: Path) -> None:
    """Workflow with pull_request as dict key triggers on PR."""
    _create_workflow(
        tmp_path,
        "ci.yml",
        """
name: CI
on:
  pull_request:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: cargo test
""",
    )
    signals = parse_github_actions(tmp_path)
    assert signals.triggers_on_pr is True


def test_push_only_no_pr(tmp_path: Path) -> None:
    """Workflow with push-only trigger reports no PR trigger."""
    _create_workflow(
        tmp_path,
        "ci.yml",
        """
name: CI
on:
  push:
    branches: [main]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo "build"
""",
    )
    signals = parse_github_actions(tmp_path)
    assert signals.triggers_on_pr is False


def test_no_workflows_directory(tmp_path: Path) -> None:
    """No .github/workflows/ directory returns empty signals."""
    signals = parse_github_actions(tmp_path)
    assert signals.ci_exists is False
    assert signals.runs_tests is False


def test_empty_workflows_directory(tmp_path: Path) -> None:
    """Empty workflows directory returns empty signals."""
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    signals = parse_github_actions(tmp_path)
    assert signals.ci_exists is False


def test_malformed_yaml_skipped(tmp_path: Path) -> None:
    """Malformed YAML is skipped; valid files still processed."""
    _create_workflow(tmp_path, "bad.yml", "{{{{invalid yaml")
    _create_workflow(
        tmp_path,
        "good.yml",
        """
name: CI
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: pytest
""",
    )
    signals = parse_github_actions(tmp_path)
    assert signals.ci_exists is True
    assert signals.runs_tests is True


def test_typecheck_patterns(tmp_path: Path) -> None:
    """Various typecheck commands are detected."""
    _create_workflow(
        tmp_path,
        "ci.yml",
        """
name: CI
on: push
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - run: npx tsc --noEmit
""",
    )
    signals = parse_github_actions(tmp_path)
    assert signals.runs_typecheck is True


def test_format_check_prettier(tmp_path: Path) -> None:
    """Prettier format check is detected."""
    _create_workflow(
        tmp_path,
        "ci.yml",
        """
name: CI
on: push
jobs:
  fmt:
    runs-on: ubuntu-latest
    steps:
      - run: npx prettier --check .
""",
    )
    signals = parse_github_actions(tmp_path)
    assert signals.runs_format_check is True


def test_rust_tools_detected(tmp_path: Path) -> None:
    """Rust cargo tools are detected."""
    _create_workflow(
        tmp_path,
        "ci.yml",
        """
name: CI
on: [push, pull_request]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - run: cargo test
      - run: cargo clippy -- -D warnings
      - run: cargo fmt -- --check
      - run: cargo check
""",
    )
    signals = parse_github_actions(tmp_path)
    assert signals.runs_tests is True
    assert signals.runs_lint is True
    assert signals.runs_format_check is True
    assert signals.runs_typecheck is True
