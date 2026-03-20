## ADDED Requirements

### Requirement: Statusline shows repo sync status
The harness SHALL provide a statusline script that displays whether the default branch has moved on origin since the last fetch. The script SHALL use `git ls-remote origin refs/heads/<default-branch>` to check the remote state and compare against the local `git rev-parse origin/<default-branch>` SHA. Results SHALL be cached for 30 seconds to avoid excessive network calls. The cache file SHALL be keyed by the SHA-256 of the absolute repo path, truncated to 12 hex characters, stored at `/tmp/harness-sync-cache-<hash>`.

#### Scenario: Default branch detection
- **WHEN** the statusline script determines the default branch
- **THEN** it SHALL check `git symbolic-ref refs/remotes/origin/HEAD`, falling back to `main`, then `master`

#### Scenario: Repo is in sync
- **WHEN** the local `origin/<default-branch>` SHA matches the remote `refs/heads/<default-branch>` SHA
- **THEN** the statusline SHALL display an "in sync" indicator

#### Scenario: Default branch has moved on origin
- **WHEN** the local `origin/<default-branch>` SHA does not match the remote `refs/heads/<default-branch>` SHA
- **THEN** the statusline SHALL display a "behind" indicator (e.g., `↑ behind origin`)

#### Scenario: Network unavailable
- **WHEN** `git ls-remote` fails due to network error or timeout
- **THEN** the statusline SHALL display a neutral indicator (e.g., `? sync unknown`) and SHALL NOT block or error

#### Scenario: Cache is fresh
- **WHEN** a cached result exists and is less than 30 seconds old
- **THEN** the statusline SHALL use the cached result without making a network call

#### Scenario: Not a git repo
- **WHEN** the working directory is not a git repository
- **THEN** the statusline SHALL omit the sync indicator entirely

### Requirement: Sync skill pulls latest changes
The harness SHALL provide a `/sync` custom slash command that pulls the latest changes from origin. For user working trees, it SHALL use `git pull --ff-only`. For harness-owned clones (detected by a `.harness-managed` marker file in the repo root), it SHALL use `git fetch origin && git reset --hard origin/<default-branch>`.

#### Scenario: Sync user working tree
- **WHEN** `/sync` is invoked and no `.harness-managed` marker file exists in the repo root
- **THEN** the command SHALL run `git pull --ff-only` and report the result

#### Scenario: Sync harness clone
- **WHEN** `/sync` is invoked and a `.harness-managed` marker file exists in the repo root
- **THEN** the command SHALL run `git fetch origin && git reset --hard origin/<default-branch>`

#### Scenario: Fast-forward fails on user working tree
- **WHEN** `git pull --ff-only` fails because branches have diverged
- **THEN** the command SHALL report the failure and suggest manual resolution (e.g., `git pull --rebase`)

#### Scenario: Uncommitted changes in user working tree
- **WHEN** `/sync` is invoked and the working tree has uncommitted changes
- **THEN** the command SHALL warn the user and abort without modifying the working tree

#### Scenario: Sync reports changes
- **WHEN** sync completes successfully and new commits were pulled
- **THEN** the command SHALL report a summary of what changed (e.g., number of new commits)
