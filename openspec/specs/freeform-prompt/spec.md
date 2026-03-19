# freeform-prompt Specification

## Purpose
TBD - created by archiving change unspecced-tasks. Update Purpose after archive.
## Requirements
### Requirement: CLI accepts --prompt as alternative to --change
The `harness run` command SHALL accept a `--prompt` flag that provides a freeform task description. Exactly one of `--prompt` or `--change` MUST be provided.

#### Scenario: --prompt provided without --change
- **WHEN** the user runs `harness run --prompt "Fix bug in auth module" --repo ./path`
- **THEN** the pipeline SHALL start with the freeform prompt and no OpenSpec change

#### Scenario: --change provided without --prompt
- **WHEN** the user runs `harness run --change add-logging --repo ./path`
- **THEN** the pipeline SHALL work exactly as it does today (no behavior change)

#### Scenario: Both --prompt and --change provided
- **WHEN** the user provides both `--prompt` and `--change`
- **THEN** the CLI SHALL exit with an error message: "Specify either --change or --prompt, not both"

#### Scenario: Neither --prompt nor --change provided
- **WHEN** the user provides neither `--prompt` nor `--change`
- **THEN** the CLI SHALL exit with an error message: "Specify either --change or --prompt"

### Requirement: Worker receives freeform prompt directly
When `--prompt` is used, the worker SHALL receive the prompt as its user prompt. The system prompt SHALL be a generic implementation role, not the opsx-apply instruction.

#### Scenario: Worker prompt in freeform mode
- **WHEN** the pipeline runs with `--prompt "Add retry logic to the API client"`
- **THEN** the worker's user prompt SHALL be "Add retry logic to the API client" and the system prompt SHALL NOT contain "opsx-apply" or reference an OpenSpec change

#### Scenario: Worker prompt in change mode
- **WHEN** the pipeline runs with `--change add-logging`
- **THEN** the worker's user prompt and system prompt SHALL be identical to current behavior (opsx-apply instruction)

### Requirement: Validation skips OpenSpec directory check for --prompt
When `--prompt` is used, the harness SHALL NOT validate that an OpenSpec change directory exists. All other validations (git repo, claude CLI, gh CLI) SHALL still apply.

#### Scenario: Prompt mode skips change directory validation
- **WHEN** the user runs `harness run --prompt "Fix typo in README" --repo ./path`
- **THEN** the harness SHALL NOT check for `openspec/changes/` directories

#### Scenario: Change mode still validates directory
- **WHEN** the user runs `harness run --change nonexistent --repo ./path`
- **THEN** the harness SHALL exit with an error about the missing change directory

### Requirement: Branch naming for prompted runs
When `--prompt` is used, the worktree branch SHALL be `harness/prompt-{slug}` where `{slug}` is a sanitized version of the prompt: lowercase, non-alphanumeric characters replaced with hyphens, consecutive hyphens collapsed, leading/trailing hyphens stripped, truncated to at most 50 characters.

#### Scenario: Branch name from prompt
- **WHEN** the prompt is "Fix the auth bug in issue #42"
- **THEN** the branch SHALL be `harness/prompt-fix-the-auth-bug-in-issue-42`

#### Scenario: Long prompt truncated
- **WHEN** the prompt is longer than 50 characters
- **THEN** the branch slug SHALL use at most 50 characters

#### Scenario: Multiline prompt uses first line only
- **WHEN** the prompt is "Fix the auth bug\nAlso update tests"
- **THEN** the branch slug SHALL be derived from "Fix the auth bug" (first line only)

### Requirement: PR title derived from prompt
When `--prompt` is used, the PR title SHALL be `[harness] {first_line_of_prompt}` truncated to 72 characters. The full prompt SHALL be included in the PR body.

#### Scenario: PR title from short prompt
- **WHEN** the prompt is "Fix the auth bug"
- **THEN** the PR title SHALL be `[harness] Fix the auth bug`

#### Scenario: PR title from long prompt
- **WHEN** the prompt's first line is longer than 62 characters (72 minus the 10-char `[harness] ` prefix)
- **THEN** the full PR title (including the `[harness] ` prefix) SHALL be at most 72 characters

#### Scenario: Multiline prompt PR title uses first line
- **WHEN** the prompt is "Fix the auth bug\nAlso update tests"
- **THEN** the PR title SHALL be `[harness] Fix the auth bug` and the PR body SHALL contain the full prompt

### Requirement: OpenSpec review skipped for prompted runs
When `--prompt` is used (no change name), the OpenSpec review stage SHALL be skipped entirely. Review agents (bug hunter, test reviewer, quality reviewer) SHALL still run.

#### Scenario: No OpenSpec review for prompted run
- **WHEN** the pipeline runs with `--prompt`
- **THEN** the `_run_openspec_review` stage SHALL be skipped and no archive check performed

#### Scenario: Review agents still run for prompted run
- **WHEN** the pipeline runs with `--prompt` and `--skip-review` is NOT set
- **THEN** review agents (bug hunter, test reviewer, quality reviewer) SHALL still be dispatched

### Requirement: Dry-run works with --prompt
When `--dry-run` is used with `--prompt`, the plan output SHALL show the prompt text instead of the change name.

#### Scenario: Dry-run with prompt
- **WHEN** the user runs `harness run --prompt "Fix typo" --repo ./path --dry-run`
- **THEN** the output SHALL show the prompt text and the derived branch name `harness/prompt-fix-typo`

