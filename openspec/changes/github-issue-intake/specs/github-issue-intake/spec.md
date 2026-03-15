## ADDED Requirements

### Requirement: --issue flag accepts a GitHub issue number
The `harness run` command SHALL accept an `--issue` flag with a GitHub issue number. It is mutually exclusive with `--change` and `--prompt`.

#### Scenario: --issue provided
- **WHEN** the user runs `harness run --issue 42 --repo owner/repo`
- **THEN** the harness SHALL read issue #42 and dispatch based on its content

#### Scenario: --issue with --change
- **WHEN** the user provides both `--issue` and `--change`
- **THEN** the CLI SHALL exit with an error: "Specify only one of --change, --prompt, or --issue"

#### Scenario: --issue with --prompt
- **WHEN** the user provides both `--issue` and `--prompt`
- **THEN** the CLI SHALL exit with an error: "Specify only one of --change, --prompt, or --issue"

### Requirement: Read issue via gh CLI
The harness SHALL read the issue using `gh issue view <number> --json title,body,labels,state` in the repo's working directory.

#### Scenario: Issue read successfully
- **WHEN** `gh issue view` returns valid JSON with title and body
- **THEN** the harness SHALL extract the title and body for dispatch

#### Scenario: Issue not found
- **WHEN** `gh issue view` returns a non-zero exit code (e.g., issue doesn't exist)
- **THEN** the CLI SHALL exit with an error: "Issue #42 not found"

#### Scenario: Issue is closed
- **WHEN** the issue has `state: "CLOSED"`
- **THEN** the CLI SHALL exit with an error: "Issue #42 is already closed"

### Requirement: Detect OpenSpec change references in issue body
The harness SHALL scan the issue body for OpenSpec change references. If a reference is found and the change directory exists, the harness SHALL dispatch in `--change` mode.

#### Scenario: openspec:change-name reference found
- **WHEN** the issue body contains `openspec:add-logging` and `openspec/changes/add-logging/` exists in the repo
- **THEN** the harness SHALL dispatch as `--change add-logging`

#### Scenario: Change directory does not exist
- **WHEN** the issue body references `openspec:nonexistent` but the change directory does not exist
- **THEN** the harness SHALL fall back to `--prompt` mode using the issue title + body

#### Scenario: No change reference in body
- **WHEN** the issue body contains no OpenSpec change references
- **THEN** the harness SHALL dispatch as `--prompt` using the issue title and body as the prompt

### Requirement: Prompt constructed from issue title and body
When dispatching in `--prompt` mode from an issue, the prompt SHALL be constructed from the issue title and body.

#### Scenario: Prompt format
- **WHEN** issue #42 has title "Fix auth bug" and body "The login endpoint returns 500..."
- **THEN** the prompt SHALL be `# GitHub Issue #42: Fix auth bug\n\nThe login endpoint returns 500...`

### Requirement: --repo is required with --issue
The `--repo` flag SHALL still be required when `--issue` is used. The issue is read from the resolved repo's GitHub context.

#### Scenario: --issue without --repo
- **WHEN** the user runs `harness run --issue 42` without `--repo`
- **THEN** the CLI SHALL exit with the existing error requiring `--repo`

### Requirement: PR links to issue for automatic closure
When dispatched from an issue, the PR body SHALL include `Closes #<number>` so GitHub automatically closes the issue on merge.

#### Scenario: PR body includes closes reference
- **WHEN** the pipeline creates a PR from issue #42
- **THEN** the PR body SHALL contain `Closes #42`

### Requirement: Issue labeled with harness status
The harness SHALL label the issue at key pipeline stages. Label operations are best-effort — failure to label SHALL NOT fail the pipeline.

#### Scenario: In-progress label
- **WHEN** the pipeline starts from an issue
- **THEN** the issue SHALL be labeled `harness:in-progress` via `gh issue edit --add-label`

#### Scenario: PR-created label
- **WHEN** the pipeline creates a PR from an issue
- **THEN** the issue SHALL be labeled `harness:pr-created` and a comment SHALL be posted with the PR URL

#### Scenario: Label failure is non-fatal
- **WHEN** `gh issue edit --add-label` fails (e.g., label doesn't exist, no write permission)
- **THEN** the harness SHALL log a warning and continue
