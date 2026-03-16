"""CI workflow parsing — extract mechanical signals from GitHub Actions."""

import glob as glob_mod
from pathlib import Path

import typer
import yaml

from action_harness.assessment import CIMechanicalSignals

# Patterns for matching CI step commands against known tools.
# Each tuple: (compiled substring to match, signal field name)
_TEST_PATTERNS: list[str] = [
    "pytest",
    "npm test",
    "npm run test",
    "yarn test",
    "pnpm test",
    "cargo test",
    "go test",
    "bundle exec rake test",
    "bundle exec rspec",
    "make test",
]

_LINT_PATTERNS: list[str] = [
    "ruff check",
    "eslint",
    "npm run lint",
    "yarn lint",
    "pnpm lint",
    "cargo clippy",
    "golangci-lint",
    "rubocop",
    "flake8",
    "pylint",
]

_TYPECHECK_PATTERNS: list[str] = [
    "mypy",
    "tsc --noEmit",
    "tsc -noEmit",
    "npx tsc",
    "cargo check",
    "pyright",
    "pytype",
]

_FORMAT_PATTERNS: list[str] = [
    "ruff format --check",
    "ruff format --diff",
    "prettier --check",
    "prettier --list-different",
    "cargo fmt -- --check",
    "cargo fmt --check",
    "gofmt",
    "black --check",
    "yapf --diff",
]


def _matches_any(command: str, patterns: list[str]) -> bool:
    """Check if command contains any of the given patterns."""
    cmd_lower = command.lower()
    return any(p.lower() in cmd_lower for p in patterns)


def _extract_run_commands(workflow_data: dict[str, object]) -> list[str]:
    """Extract all 'run' commands from a workflow's jobs and steps."""
    commands: list[str] = []
    jobs = workflow_data.get("jobs")
    if not isinstance(jobs, dict):
        return commands

    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        steps = job.get("steps")
        if not isinstance(steps, list):
            continue
        for step in steps:
            if not isinstance(step, dict):
                continue
            run_cmd = step.get("run")
            if isinstance(run_cmd, str):
                commands.append(run_cmd)

    return commands


def _check_pr_trigger(workflow_data: dict[str, object]) -> bool:
    """Check if the workflow triggers on pull requests."""
    # YAML parses bare `on:` as boolean True key, so check both
    on_value = workflow_data.get("on")
    if on_value is None:
        # pyyaml may parse `on:` as True (boolean key)
        on_value = workflow_data.get(True)  # type: ignore[call-overload]
    if on_value is None:
        return False

    # on: pull_request
    if isinstance(on_value, str):
        return on_value == "pull_request"

    # on: [push, pull_request]
    if isinstance(on_value, list):
        return "pull_request" in on_value

    # on: { pull_request: ... }
    if isinstance(on_value, dict):
        return "pull_request" in on_value or "pull_request_target" in on_value

    return False


def parse_github_actions(
    repo_path: Path,
    branch_protection: bool | None = None,
) -> CIMechanicalSignals:
    """Parse GitHub Actions workflow files and return CI mechanical signals.

    Scans .github/workflows/*.yml and .github/workflows/*.yaml for CI
    configuration, trigger events, and known tool patterns.

    branch_protection is passed through from the caller (e.g. GitHub API
    check) so the returned signals object is complete.
    """
    typer.echo("[ci_parser] scanning GitHub Actions workflows", err=True)

    workflows_dir = repo_path / ".github" / "workflows"
    if not workflows_dir.is_dir():
        typer.echo("[ci_parser] no .github/workflows/ directory found", err=True)
        return CIMechanicalSignals(branch_protection=branch_protection)

    yml_files = glob_mod.glob(str(workflows_dir / "*.yml")) + glob_mod.glob(
        str(workflows_dir / "*.yaml")
    )

    if not yml_files:
        typer.echo("[ci_parser] no workflow files found", err=True)
        return CIMechanicalSignals(branch_protection=branch_protection)

    ci_exists = True
    triggers_on_pr = False
    runs_tests = False
    runs_lint = False
    runs_typecheck = False
    runs_format_check = False

    for yml_file in yml_files:
        file_path = Path(yml_file)
        try:
            content = file_path.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
        except (OSError, yaml.YAMLError) as exc:
            typer.echo(
                f"[ci_parser] warning: skipping {file_path.name}: {exc}",
                err=True,
            )
            continue

        if not isinstance(data, dict):
            continue

        if _check_pr_trigger(data):
            triggers_on_pr = True

        commands = _extract_run_commands(data)
        for cmd in commands:
            if not runs_tests and _matches_any(cmd, _TEST_PATTERNS):
                runs_tests = True
            if not runs_lint and _matches_any(cmd, _LINT_PATTERNS):
                runs_lint = True
            if not runs_typecheck and _matches_any(cmd, _TYPECHECK_PATTERNS):
                runs_typecheck = True
            if not runs_format_check and _matches_any(cmd, _FORMAT_PATTERNS):
                runs_format_check = True

    typer.echo(
        f"[ci_parser] done: ci_exists={ci_exists}, pr={triggers_on_pr}, "
        f"tests={runs_tests}, lint={runs_lint}, typecheck={runs_typecheck}, "
        f"format={runs_format_check}",
        err=True,
    )

    return CIMechanicalSignals(
        ci_exists=ci_exists,
        triggers_on_pr=triggers_on_pr,
        runs_tests=runs_tests,
        runs_lint=runs_lint,
        runs_typecheck=runs_typecheck,
        runs_format_check=runs_format_check,
        branch_protection=branch_protection,
    )
