## Why

The repo has no CI. The harness runs eval locally (pytest, ruff, mypy) but there's nothing catching regressions on push or PR. The codebase assessment scores CI guardrails at 0/100. Adding CI provides a safety net — if the harness eval passed but something is platform-dependent or the worktree had local state, CI catches it. It also enables `--auto-merge --wait-for-ci` to be meaningful.

## What Changes

- Add `.github/workflows/ci.yml` with a single job that runs the eval suite on PRs and pushes to main
- Uses `astral-sh/setup-uv` with caching for fast installs
- Runs: `uv sync`, `uv run pytest -v`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src/`
- No Python version matrix (single version, matches pyproject.toml target)
- No secrets required (all tests mock external CLIs)
- No branch protection rules (future enhancement)

## Capabilities

### New Capabilities
- `ci-workflow`: GitHub Actions workflow that runs the eval suite on PRs and pushes to main.

### Modified Capabilities
None

## Impact

- New file: `.github/workflows/ci.yml`
- No code changes — the workflow runs existing eval commands
- Codebase assessment CI guardrails score will improve from 0 to ~80+
