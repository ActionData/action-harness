# workspace-management Specification

## Purpose
TBD - created by archiving change workspace-management. Update Purpose after archive.
## Requirements
### Requirement: Accept remote repo references
The CLI SHALL accept `--repo` as a local path, GitHub `owner/repo` shorthand, or full GitHub URL. When given a remote reference, the harness SHALL clone the repo to `$HARNESS_HOME/projects/<repo-name>/repo/` if not already cloned.

#### Scenario: GitHub shorthand
- **WHEN** the operator runs `action-harness run --change foo --repo ActionData/action-harness`
- **THEN** the harness clones to `$HARNESS_HOME/projects/action-harness/repo/` (if not present), fetches latest, and proceeds

#### Scenario: Full URL
- **WHEN** the operator runs with `--repo https://github.com/user/my-app`
- **THEN** the harness clones to `$HARNESS_HOME/projects/my-app/repo/` and proceeds

#### Scenario: Local path unchanged
- **WHEN** the operator runs with `--repo .` or `--repo /abs/path`
- **THEN** the harness uses the local path directly without cloning (existing behavior)

#### Scenario: Clone fails
- **WHEN** the operator runs with `--repo user/nonexistent-repo` and the clone command fails
- **THEN** the harness logs the git error to stderr and exits with a non-zero exit code without proceeding to pipeline stages

#### Scenario: Repo already cloned
- **WHEN** the operator runs with `--repo user/my-app` and `$HARNESS_HOME/projects/my-app/repo/` already exists
- **THEN** the harness runs `git fetch origin` to update, then proceeds without re-cloning

### Requirement: Create workspaces in harness home
Workspaces (worktrees) SHALL be created at `$HARNESS_HOME/projects/<repo-name>/workspaces/<change-name>/` for managed repos. The workspace SHALL be a git worktree branched from the repo's default branch.

#### Scenario: Workspace created in project directory
- **WHEN** the pipeline creates a worktree for change `add-logging` on repo `my-app`
- **THEN** the worktree is at `$HARNESS_HOME/projects/my-app/workspaces/add-logging/`

#### Scenario: Workspace has full repo context
- **WHEN** a workspace is created from a repo that has `.claude/` skills and `CLAUDE.md`
- **THEN** the workspace contains those files and the agent can access them

### Requirement: Handle repo name collisions
When two different repos have the same name (e.g., `orgA/utils` and `orgB/utils`), the harness SHALL detect the collision and use `owner-repo` as the directory name instead of just `repo`.

#### Scenario: Name collision detected
- **WHEN** `orgA/utils` is already cloned and the operator runs with `--repo orgB/utils`
- **THEN** the second repo is cloned to `$HARNESS_HOME/projects/orgB-utils/repo/` and the collision is logged

### Requirement: Configurable harness home directory
The harness home directory SHALL default to `~/harness/`. It SHALL be configurable via `HARNESS_HOME` environment variable or `--harness-home` CLI flag. The CLI flag SHALL take precedence over the env var.

#### Scenario: Default harness home
- **WHEN** the operator runs without `HARNESS_HOME` or `--harness-home`
- **THEN** the harness uses `~/harness/` as the home directory

#### Scenario: Env var override
- **WHEN** `HARNESS_HOME=/data/harness` is set
- **THEN** repos are cloned to `/data/harness/projects/<name>/repo/` and workspaces created in `/data/harness/projects/<name>/workspaces/`

#### Scenario: CLI flag overrides env var
- **WHEN** `HARNESS_HOME=/data/harness` is set and `--harness-home /other` is passed
- **THEN** the harness uses `/other/` as the home directory

### Requirement: Clean command removes workspaces
The CLI SHALL provide a `clean` subcommand that removes workspaces from the project directory. It SHALL NOT remove the repo clone or other project state.

#### Scenario: Clean specific workspace
- **WHEN** the operator runs `action-harness clean --repo user/app --change fix-bug`
- **THEN** the workspace at `$HARNESS_HOME/projects/app/workspaces/fix-bug/` is removed and the git worktree is pruned

#### Scenario: Clean all workspaces for a repo
- **WHEN** the operator runs `action-harness clean --repo user/app`
- **THEN** all workspaces under `$HARNESS_HOME/projects/app/workspaces/` are removed

#### Scenario: Clean all workspaces
- **WHEN** the operator runs `action-harness clean --all`
- **THEN** all workspaces under all `$HARNESS_HOME/projects/*/workspaces/` directories are removed but repo clones and other project state are preserved

### Requirement: Fetch before workspace creation
When using a managed repo, the harness SHALL run `git fetch origin` in `$HARNESS_HOME/projects/<repo-name>/repo/` before creating a workspace worktree.

#### Scenario: Fetch on managed repo
- **WHEN** the pipeline creates a workspace for a managed repo
- **THEN** `git fetch origin` is run in `$HARNESS_HOME/projects/<repo-name>/repo/` before the worktree is created
