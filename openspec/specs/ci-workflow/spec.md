# ci-workflow Specification

## Purpose
TBD - created by archiving change add-ci. Update Purpose after archive.
## Requirements
### Requirement: CI workflow runs eval suite on PRs and pushes to main
The repo SHALL have a GitHub Actions workflow at `.github/workflows/ci.yml` that runs the eval suite on pull requests and pushes to the main branch.

#### Scenario: PR triggers CI
- **WHEN** a pull request is opened or updated
- **THEN** the CI workflow SHALL run and execute all eval commands

#### Scenario: Push to main triggers CI
- **WHEN** a commit is pushed to the main branch
- **THEN** the CI workflow SHALL run and execute all eval commands

#### Scenario: Push to non-main branch does not trigger CI
- **WHEN** a commit is pushed to a branch other than main (without a PR)
- **THEN** the CI workflow SHALL NOT run

### Requirement: CI runs all five eval commands
The CI workflow SHALL run the same eval commands defined in CLAUDE.md, in order: `uv sync`, `uv run pytest -v`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src/`.

#### Scenario: All commands run
- **WHEN** the CI workflow runs
- **THEN** it SHALL execute `uv sync`, `uv run pytest -v`, `uv run ruff check .`, `uv run ruff format --check .`, and `uv run mypy src/` in that order

#### Scenario: Failure on any command fails the workflow
- **WHEN** any eval command returns a non-zero exit code
- **THEN** the CI workflow SHALL fail and report the failing step

### Requirement: CI uses uv with dependency caching
The CI workflow SHALL use `astral-sh/setup-uv` with caching enabled to avoid re-downloading uv and dependencies on every run.

#### Scenario: Cache hit on subsequent runs
- **WHEN** the workflow runs and the uv.lock file has not changed since the last run
- **THEN** dependencies SHALL be restored from cache (no network downloads)

### Requirement: CI requires no secrets
The CI workflow SHALL work without any configured secrets or API tokens. All tests mock external CLI calls.

#### Scenario: Fresh repo fork runs CI successfully
- **WHEN** someone forks the repo and opens a PR
- **THEN** CI SHALL pass without configuring any secrets

