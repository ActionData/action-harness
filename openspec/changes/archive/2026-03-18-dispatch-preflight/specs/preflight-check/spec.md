## ADDED Requirements

### Requirement: Detect archived OpenSpec changes
The pipeline SHALL check if the OpenSpec change has been archived before starting work. If `openspec/archive/<change-name>/` exists in the repo, the pipeline SHALL bail early with a message indicating the change is already completed and archived.

#### Scenario: Change is archived
- **WHEN** the pipeline starts for change `deduplicate-run-stats` and `openspec/archive/deduplicate-run-stats/` exists
- **THEN** the pipeline logs "change 'deduplicate-run-stats' is already archived — skipping" and returns early without creating a worktree

#### Scenario: Change is not archived
- **WHEN** the pipeline starts for change `new-feature` and no archive directory exists for it
- **THEN** the pipeline continues to the next preflight check

### Requirement: Detect merged PRs with verification
The pipeline SHALL check for merged PRs matching the change name via `gh pr list`. When a merged PR is found, the pipeline SHALL verify that the PR's merge commit is an ancestor of the default branch HEAD. If verified, the pipeline SHALL bail early.

#### Scenario: Merged PR with commits on default branch
- **WHEN** the pipeline starts for change `deduplicate-run-stats` and a merged PR exists for branch `harness/deduplicate-run-stats` and the merge commit is an ancestor of `main` HEAD
- **THEN** the pipeline logs "change 'deduplicate-run-stats' already merged (PR #57)" and returns early

#### Scenario: Merged PR but commits not on default branch
- **WHEN** a merged PR exists but the merge commit is not an ancestor of the default branch HEAD (e.g., the PR was reverted)
- **THEN** the pipeline logs a warning and continues with a suffixed branch name

#### Scenario: gh CLI not available
- **WHEN** the `gh` CLI is not installed or not authenticated
- **THEN** the pipeline logs a warning and skips the merged-PR check, continuing to worktree creation

### Requirement: Handle stale remote branches
The pipeline SHALL check for existing remote branches matching `harness/<change-name>`. When a stale remote branch exists and the change is not verified complete, the pipeline SHALL use an incremented branch name (`harness/<change-name>-2`, `-3`, etc.).

#### Scenario: Stale remote branch with no merged PR
- **WHEN** the remote branch `harness/deduplicate-run-stats` exists but there is no merged PR for it
- **THEN** the pipeline uses branch name `harness/deduplicate-run-stats-2` and logs "stale remote branch detected, using harness/deduplicate-run-stats-2"

#### Scenario: Multiple stale remote branches
- **WHEN** remote branches `harness/my-change`, `harness/my-change-2`, and `harness/my-change-3` all exist
- **THEN** the pipeline uses `harness/my-change-4`

#### Scenario: No stale remote branch
- **WHEN** no remote branch matching the change name exists
- **THEN** the pipeline uses the default branch name `harness/<change-name>`

### Requirement: Preflight recorded in manifest
The preflight check SHALL be recorded as a stage in the run manifest with its own timing, status, and detail message.

#### Scenario: Preflight clears
- **WHEN** the preflight check finds no prior completion signals
- **THEN** the manifest includes a preflight stage with status "clear"

#### Scenario: Preflight bails
- **WHEN** the preflight check determines the change is already complete
- **THEN** the manifest includes a preflight stage with status "completed" and the pipeline returns early with a success result

### Requirement: Skip completion checks for prompt dispatches
The pipeline SHALL skip OpenSpec archive and task completion checks for `--prompt` and `--issue` dispatches since they have no prior OpenSpec state. The stale remote branch check SHALL still run.

#### Scenario: Prompt dispatch with stale branch
- **WHEN** a `--prompt` dispatch is started and a stale remote branch exists for the generated change name
- **THEN** the pipeline uses a suffixed branch name but does not check for OpenSpec archive or merged PRs
