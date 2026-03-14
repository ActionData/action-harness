## ADDED Requirements

### Requirement: PR body includes proposal context
The PR body SHALL include the "Why" section from the change's `proposal.md` if the file exists in the worktree. If the file does not exist or cannot be parsed, the section SHALL be omitted gracefully.

#### Scenario: Proposal exists
- **WHEN** a PR is created for a change that has `openspec/changes/<name>/proposal.md`
- **THEN** the PR body includes a "Background" section with the proposal's Why content

#### Scenario: Proposal missing
- **WHEN** a PR is created for a change without a proposal.md
- **THEN** the PR body omits the Background section without error

### Requirement: PR body includes diff summary
The PR body SHALL include the output of `git diff --stat` showing files changed, insertions, and deletions. The diff stat SHALL be truncated to 30 lines if longer.

#### Scenario: Diff stat included
- **WHEN** a PR is created
- **THEN** the PR body includes a "Changes" section with the diff stat output

#### Scenario: Diff stat truncated
- **WHEN** a PR is created for a branch with diff stat output exceeding 30 lines
- **THEN** the Changes section includes only the first 30 lines followed by "... (truncated)"

#### Scenario: Git diff command fails
- **WHEN** `git diff --stat` fails in the worktree (non-zero exit code)
- **THEN** the Changes section is omitted without crashing PR creation

### Requirement: PR body includes commit messages
The PR body SHALL include the output of `git log --oneline` for commits on the branch. This shows the worker's incremental progress.

#### Scenario: Commit log included
- **WHEN** a PR is created for a branch with 3 commits
- **THEN** the PR body includes a "Commits" section listing all 3 commit messages

### Requirement: PR body includes worker metadata
The PR body SHALL include worker cost (if available), duration, and the worker's self-reported observations (truncated to 500 characters).

#### Scenario: Worker metadata included
- **WHEN** a PR is created and the worker reported cost and observations
- **THEN** the PR body includes a "Worker" section with cost, duration, and observation text

#### Scenario: Worker metadata partially available
- **WHEN** a PR is created but cost is not available
- **THEN** the Worker section omits cost and includes only available fields

#### Scenario: Worker observations truncated
- **WHEN** a PR is created and worker observations exceed 500 characters
- **THEN** the Worker section includes only the first 500 characters of observations followed by "... (truncated)"

### Requirement: PR body includes eval results
The PR body SHALL include the eval pass/fail summary with command details. This is an enhancement of the existing eval section.

#### Scenario: All eval passes
- **WHEN** all eval commands pass
- **THEN** the PR body shows "All N/N eval commands passed"

#### Scenario: Eval failure
- **WHEN** eval fails
- **THEN** the PR body shows which command failed and the pass/fail counts
