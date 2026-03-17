# rollback-tags Specification

## Purpose
TBD - created by archiving change rollback-tags. Update Purpose after archive.
## Requirements
### Requirement: Pre-merge tag created immediately before PR creation
The harness SHALL create a git tag `harness/pre-merge/{label}` on the base branch HEAD immediately before creating the PR. The `{label}` is the change name or task label (prompt slug). Rolling back to this tag may also revert unrelated work that merged between PR creation and the harness PR merge.

#### Scenario: Pre-merge tag for change-based run
- **WHEN** the harness is about to create a PR for change `add-logging`
- **THEN** a tag `harness/pre-merge/add-logging` SHALL be created on the base branch HEAD before `create_pr()` is called

#### Scenario: Pre-merge tag for prompt-based run
- **WHEN** the harness is about to create a PR for task label `prompt-fix-auth-bug`
- **THEN** a tag `harness/pre-merge/prompt-fix-auth-bug` SHALL be created on the base branch HEAD

#### Scenario: Tag collision appends timestamp with microseconds
- **WHEN** a tag `harness/pre-merge/add-logging` already exists
- **THEN** the new tag SHALL be `harness/pre-merge/add-logging-{YYYYMMDD-HHMMSS-ffffff}` (with microsecond precision to avoid sub-second collisions)

### Requirement: Post-merge tag via `harness tag-shipped` command
The `harness tag-shipped` command SHALL create a git tag `harness/shipped/{label}` on the merge commit after confirming the PR was merged via `gh pr view --json mergedAt,mergeCommitSha`.

#### Scenario: Shipped tag after merge
- **WHEN** the user runs `harness tag-shipped --repo ./path --pr <url> --label add-logging` and the PR is merged
- **THEN** a tag `harness/shipped/add-logging` SHALL be created on the merge commit

#### Scenario: PR not merged yet
- **WHEN** the user runs `harness tag-shipped` and the PR is still open
- **THEN** the command SHALL exit with a message: "PR is not merged yet" and no tag SHALL be created

#### Scenario: Invalid PR URL
- **WHEN** the user runs `harness tag-shipped` with an invalid `--pr` value
- **THEN** the command SHALL exit with an error

### Requirement: Tags pushed individually to remote
The harness SHALL push each created tag individually via `git push origin <tag_name>`. It SHALL NOT use `git push origin --tags` (which would push all local tags).

#### Scenario: Tag pushed after creation
- **WHEN** a pre-merge or shipped tag is created
- **THEN** the harness SHALL run `git push origin <tag_name>` for that specific tag

#### Scenario: Push failure logged but non-fatal
- **WHEN** `git push origin <tag_name>` fails
- **THEN** the harness SHALL log a warning to stderr and continue (tag push failure does not fail the pipeline or command)

### Requirement: Rollback command reverts to tagged state
The `harness rollback` command SHALL create a single revert commit that sets the working tree to match the state captured by a `harness/pre-merge/` tag. It SHALL NOT force-push or rewrite history.

#### Scenario: Rollback to most recent pre-merge tag
- **WHEN** the user runs `harness rollback --repo ./path` without `--to`
- **THEN** the harness SHALL identify the most recent `harness/pre-merge/*` tag and create a single commit that matches the tagged tree state

#### Scenario: Rollback to specific tag
- **WHEN** the user runs `harness rollback --repo ./path --to harness/pre-merge/add-logging`
- **THEN** the harness SHALL revert to that specific tag's tree state in a single commit

#### Scenario: No pre-merge tags exist
- **WHEN** the user runs `harness rollback` but no `harness/pre-merge/*` tags exist
- **THEN** the command SHALL exit with an error: "No rollback points found"

#### Scenario: Rollback creates a single forward commit not force push
- **WHEN** the harness rolls back
- **THEN** it SHALL create exactly one commit on the current branch and SHALL NOT use `git reset --hard` or `git push --force`

#### Scenario: Dirty working tree prevents rollback
- **WHEN** the user runs `harness rollback` and the working tree has uncommitted changes
- **THEN** the command SHALL exit with an error instructing the user to commit or stash changes first

### Requirement: History command lists shipped features
The `harness history` command SHALL list all `harness/shipped/*` tags with their timestamps, commit hashes, and labels, ordered by date descending.

#### Scenario: History with shipped features
- **WHEN** the user runs `harness history --repo ./path` and there are 3 shipped tags
- **THEN** the output SHALL list all 3 tags with date, commit hash, and label, most recent first

#### Scenario: History with no shipped features
- **WHEN** the user runs `harness history --repo ./path` and there are no shipped tags
- **THEN** the output SHALL say "No harness-shipped features found"

#### Scenario: History JSON output
- **WHEN** the user runs `harness history --repo ./path --json`
- **THEN** the output SHALL be a JSON array of objects with `tag` (str), `commit` (str), `date` (ISO 8601 str), and `label` (str) fields, ordered by date descending

