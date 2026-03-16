## ADDED Requirements

### Requirement: List all workspaces

`list_workspaces(harness_home)` SHALL scan `<harness_home>/workspaces/` and return a `WorkspaceInfo` for each workspace directory. The workspace directory structure is `<harness_home>/workspaces/<repo_name>/<change_name>/`, where each `<change_name>` directory is a git worktree created by the pipeline. Each entry SHALL include: repo name, change name, path, branch name, last commit age in days, and staleness flag.

#### Scenario: Workspaces from multiple repos
- **WHEN** `~/harness/workspaces/analytics-monorepo/add-logging/` and `~/harness/workspaces/action-harness/fix-auth/` exist as git worktrees
- **THEN** `list_workspaces` returns 2 `WorkspaceInfo` objects: one with `repo_name="analytics-monorepo"`, `change_name="add-logging"`, one with `repo_name="action-harness"`, `change_name="fix-auth"`

#### Scenario: No workspaces
- **WHEN** `~/harness/workspaces/` is empty or does not exist
- **THEN** `list_workspaces` returns an empty list

### Requirement: Staleness detection

A workspace SHALL be marked stale when the last commit on its branch is older than 7 days AND there is no open PR for the branch. The PR check SHALL use `gh pr list --head <branch> --json number --limit 1` and is best-effort — if `gh` is unavailable or the command fails, staleness is determined by time alone.

#### Scenario: Recent workspace is not stale
- **WHEN** the last commit on the workspace branch is 2 days old
- **THEN** `stale` is `False`

#### Scenario: Old workspace with no PR is stale
- **WHEN** the last commit on the workspace branch is 10 days old and no open PR exists for the branch
- **THEN** `stale` is `True`

#### Scenario: Old workspace with open PR is not stale
- **WHEN** the last commit on the workspace branch is 10 days old but an open PR exists for the branch
- **THEN** `stale` is `False`

#### Scenario: gh CLI unavailable
- **WHEN** `gh` is not installed or fails
- **THEN** staleness is determined by commit age alone (stale if >7 days)

### Requirement: CLI workspaces command

`harness workspaces` SHALL print all workspaces across all repos with repo name, change name, branch, age, and staleness indicator.

#### Scenario: Formatted output
- **WHEN** the user runs `harness workspaces` with workspace `analytics-monorepo/add-logging` (2 days old) and `action-harness/fix-auth` (10 days old, stale)
- **THEN** the output contains lines showing each workspace with its age, and stale workspaces are marked with `(stale)`: e.g., `action-harness/fix-auth    harness/fix-auth    10d ago  (stale)`

#### Scenario: JSON output
- **WHEN** the user runs `harness workspaces --json`
- **THEN** the output is a JSON array of `WorkspaceInfo` objects
