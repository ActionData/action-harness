## Context

The repo has zero CI. All quality checks run locally via the harness eval or manual `uv run pytest`. The codebase assessment scores CI guardrails at 0/100. This is a straightforward GitHub Actions workflow — no complex infrastructure needed.

## Goals / Non-Goals

**Goals:**
- GitHub Actions workflow triggered on PRs and pushes to main
- Runs the same 5 eval commands from CLAUDE.md
- Caches uv and Python dependencies for fast subsequent runs
- Works without secrets (all tests mock external CLIs)

**Non-Goals:**
- Python version matrix (single version is sufficient)
- Branch protection rules (future enhancement)
- Coverage reporting (separate change)
- Publishing or deployment steps

## Decisions

### 1. Single workflow, single job

One file: `.github/workflows/ci.yml`. One job: `check`. No matrix, no parallel jobs. The eval suite runs in ~7 seconds locally — parallelizing would add overhead without meaningful speedup.

### 2. `astral-sh/setup-uv` with caching enabled

Use the official uv GitHub Action (`astral-sh/setup-uv@v4`) with `enable-cache: true`. This caches the uv binary and the dependency cache (`~/.cache/uv`), so subsequent runs skip downloading packages. Python is installed via uv (`uv python install`) which is also cached.

### 3. Triggers: pull_request + push to main

```yaml
on:
  pull_request:
  push:
    branches: [main]
```

PRs get checked before merge. Pushes to main confirm the post-merge state is clean (catches merge conflict issues).

### 4. Python version from pyproject.toml

Let uv handle Python version selection from `pyproject.toml` (`requires-python = ">=3.13"`). Don't hardcode the version in the workflow — uv reads it from the project config.

## Risks / Trade-offs

- [Runner availability] GitHub-hosted ubuntu-latest may have different system packages than macOS dev → Mitigation: the test suite is pure Python with mocked subprocesses, no platform-specific code.
- [Cache invalidation] uv cache may become stale → Mitigation: `astral-sh/setup-uv` handles cache key based on lockfile hash.
