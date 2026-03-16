## ADDED Requirements

### Requirement: Parse CI workflow files
The mechanical scan SHALL parse `.github/workflows/*.yml` files to extract CI pipeline details including trigger events, job names, and run steps.

#### Scenario: GitHub Actions workflow with test and lint steps
- **WHEN** the repo contains `.github/workflows/ci.yml` with steps that run `pytest` and `ruff check`
- **THEN** the scan SHALL report `runs_tests: true` and `runs_lint: true`

#### Scenario: CI triggers on pull requests
- **WHEN** a workflow has `on: pull_request` or `on: [push, pull_request]`
- **THEN** the scan SHALL report `triggers_on_pr: true`

#### Scenario: CI only triggers on push to main
- **WHEN** a workflow has `on: push` with `branches: [main]` and no pull_request trigger
- **THEN** the scan SHALL report `triggers_on_pr: false`

#### Scenario: No CI workflows present
- **WHEN** the repo has no `.github/workflows/` directory or no `.yml` files in it
- **THEN** the scan SHALL report `ci_exists: false` and all CI signals as false/absent

#### Scenario: Workflow with type checking
- **WHEN** a workflow step runs `mypy`, `tsc --noEmit`, or `cargo check`
- **THEN** the scan SHALL report `runs_typecheck: true`

#### Scenario: Malformed YAML workflow file
- **WHEN** a workflow YAML file is malformed (invalid YAML)
- **THEN** the scan SHALL skip that file, log a warning, and continue processing other workflow files

#### Scenario: Workflow with format checking
- **WHEN** a workflow step runs `ruff format --check`, `prettier --check`, or `cargo fmt -- --check`
- **THEN** the scan SHALL report `runs_format_check: true`

### Requirement: Detect dependency lockfiles
The mechanical scan SHALL check for the presence of dependency lockfiles appropriate to the detected ecosystem.

#### Scenario: Python repo with uv.lock
- **WHEN** the repo contains `uv.lock`
- **THEN** the scan SHALL report `lockfile_present: true` with `lockfile: "uv.lock"`

#### Scenario: JavaScript repo with package-lock.json
- **WHEN** the repo contains `package-lock.json`
- **THEN** the scan SHALL report `lockfile_present: true` with `lockfile: "package-lock.json"`

#### Scenario: No lockfile present
- **WHEN** the repo contains no recognized lockfile
- **THEN** the scan SHALL report `lockfile_present: false`

### Requirement: Analyze test structure
The mechanical scan SHALL count test files and test functions to assess testing coverage structurally.

#### Scenario: Python repo with test files
- **WHEN** the repo contains files matching `test_*.py` or `*_test.py`
- **THEN** the scan SHALL report the count of test files and the count of functions matching `def test_`

#### Scenario: No test files found
- **WHEN** the repo contains no files matching test naming conventions
- **THEN** the scan SHALL report `test_files: 0` and `test_functions: 0`

### Requirement: Check branch protection via GitHub API
The mechanical scan SHALL optionally query the GitHub API for branch protection rules on the default branch.

#### Scenario: Branch protection with required status checks
- **WHEN** `gh api` returns branch protection with required status checks
- **THEN** the scan SHALL report `required_status_checks: true` and list the check names

#### Scenario: No branch protection configured
- **WHEN** `gh api` returns 404 or no protection rules
- **THEN** the scan SHALL report `branch_protection: false`

#### Scenario: GitHub CLI not available or not authenticated
- **WHEN** the `gh` command is not available or returns an auth error
- **THEN** the scan SHALL skip branch protection checks and report `branch_protection: null` (unable to assess)

### Requirement: Detect context files and tooling markers
The mechanical scan SHALL check for files that provide agent context and tooling configuration.

#### Scenario: CLAUDE.md present
- **WHEN** the repo contains `CLAUDE.md`
- **THEN** the scan SHALL report `claude_md: true`

#### Scenario: MCP configuration present
- **WHEN** the repo contains `.claude/mcp*.json` or similar MCP config files
- **THEN** the scan SHALL report `mcp_configured: true`

#### Scenario: Docker configuration present
- **WHEN** the repo contains `Dockerfile` or `docker-compose.yml`/`compose.yml`
- **THEN** the scan SHALL report `docker_configured: true`

#### Scenario: Claude Code skills present
- **WHEN** the repo contains `.claude/commands/` with skill files
- **THEN** the scan SHALL report `skills_present: true`
