# human-task-awareness Specification

## Purpose
TBD - created by archiving change openspec-review-human-tasks. Update Purpose after archive.
## Requirements
### Requirement: Recognize HUMAN tagged tasks
The openspec-review agent SHALL distinguish tasks tagged with `[HUMAN]` from regular tasks. Tasks containing `[HUMAN]` in the task text are expected to be incomplete when the agent reviews.

#### Scenario: All regular tasks complete, human tasks remain
- **WHEN** tasks.md has 7 of 10 tasks `[x]` and the 3 incomplete tasks all contain `[HUMAN]`
- **THEN** the agent reports status `needs-human` instead of `findings`

#### Scenario: Regular tasks incomplete
- **WHEN** tasks.md has incomplete tasks that do NOT contain `[HUMAN]`
- **THEN** the agent reports status `findings` with the incomplete tasks listed

#### Scenario: All tasks complete including human tasks
- **WHEN** all tasks including `[HUMAN]` tasks are `[x]`
- **THEN** the agent reports status `approved` and archives normally

### Requirement: needs-human status in agent output
The review agent SHALL support `needs-human` as a valid `status` value in its JSON output, alongside `approved` and `findings`. The output SHALL include `human_tasks_remaining` (int) when status is `needs-human`. The fields `validation_passed` and `semantic_review_passed` SHALL still be populated normally.

#### Scenario: needs-human JSON output
- **WHEN** the agent determines only human tasks remain
- **THEN** the JSON output has `status: "needs-human"`, `archived: false`, `human_tasks_remaining` with the count, and `validation_passed: true`

### Requirement: Pipeline treats needs-human as success
When the openspec-review agent returns `needs-human`, the pipeline SHALL report success (exit code 0), set `needs_human=True` on the manifest, post a PR comment listing the remaining human tasks with their descriptions, and add a `needs-human` label to the PR.

#### Scenario: Pipeline success with needs-human
- **WHEN** the openspec-review returns `needs-human`
- **THEN** the pipeline exits with code 0 and `manifest.needs_human` is `True`

#### Scenario: PR labeled and commented for human action
- **WHEN** the openspec-review returns `needs-human` with 3 human tasks
- **THEN** the PR has a `needs-human` label and a comment listing the 3 remaining human tasks

### Requirement: No archival on needs-human
The agent SHALL NOT archive the change when status is `needs-human`. Archival happens only when all tasks (including human tasks) are complete.

#### Scenario: Archive skipped on needs-human
- **WHEN** the agent reports `needs-human`
- **THEN** `archived` is `false` and no archive commit is made

