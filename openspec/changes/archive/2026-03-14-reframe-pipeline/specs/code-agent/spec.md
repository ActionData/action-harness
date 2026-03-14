## ADDED Requirements

### Requirement: Create isolated worktree for implementation
The system SHALL create a new git worktree for each task, branched from the repo's default branch. The branch name SHALL follow the pattern `harness/<change-name>`. All agent work MUST happen in the worktree, not the main checkout.

#### Scenario: Worktree creation
- **WHEN** the system begins implementation for change `add-logging`
- **THEN** it creates a worktree at a temporary path with branch `harness/add-logging` based on the default branch

#### Scenario: Branch already exists from previous run
- **WHEN** the system begins implementation but branch `harness/<change-name>` already exists (from a prior failed run)
- **THEN** the system removes the existing worktree (if any) and deletes the branch, then creates a fresh worktree. This makes re-runs after failure safe without manual cleanup.

#### Scenario: Worktree cleanup on failure
- **WHEN** the implementation fails and cannot be retried
- **THEN** the worktree is removed but the branch is preserved for inspection

#### Scenario: Worktree cleanup on success
- **WHEN** the implementation succeeds and the PR is created
- **THEN** the worktree is preserved until the PR is merged or closed, then cleaned up

### Requirement: Dispatch Claude Code worker with opsx:apply
The system SHALL invoke Claude Code as a subprocess in the worktree directory, instructing it to run `opsx:apply` on the target change. The worker MUST receive a system prompt that includes the change name and instructions to implement all tasks, commit incrementally, and self-validate.

#### Scenario: Successful worker dispatch
- **WHEN** the system dispatches a worker for change `add-logging`
- **THEN** Claude Code is invoked via CLI with the worktree as working directory, `--output-format json`, and a system prompt to run `opsx:apply` for the change

#### Scenario: Worker output capture
- **WHEN** the Claude Code worker completes (success or failure)
- **THEN** the system captures the full JSON output including cost, duration, and result text

### Requirement: Verify worker produced commits
The system SHALL check that the worktree branch has at least one commit ahead of the base branch after the worker completes. If no commits exist, the system SHALL treat this as a failure (the worker did not produce useful work) and either retry or exit with an error.

#### Scenario: Worker produces commits
- **WHEN** the worker completes and the worktree branch has commits ahead of the base
- **THEN** the system proceeds to evaluation

#### Scenario: Worker produces no commits
- **WHEN** the worker completes but the worktree branch has zero commits ahead of the base
- **THEN** the system treats this as a failure, formats feedback ("No commits were produced. Review the change specs and implement the required tasks."), and retries (subject to max retry cap)

### Requirement: Validate Claude Code CLI is available
The system SHALL verify that the `claude` CLI is available in PATH before attempting worker dispatch. If not found, the system SHALL exit with a clear error message.

#### Scenario: Claude CLI not found
- **WHEN** the system attempts to dispatch a worker but `claude` is not in PATH
- **THEN** the system exits with error: "Claude Code CLI not found in PATH. Install it before running action-harness."

### Requirement: Run automated evaluation after implementation
The system SHALL run eval commands (build, test, lint, type check) as subprocesses in the worktree after the worker completes. For bootstrap, the eval commands are: `uv run pytest -v`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src/`. Exit code 0 means pass; nonzero means fail.

#### Scenario: All eval passes
- **WHEN** all eval commands exit with code 0
- **THEN** the system marks eval as passed and proceeds to PR creation

#### Scenario: Eval failure triggers retry
- **WHEN** any eval command fails
- **THEN** the system captures stdout/stderr, formats a structured feedback prompt including the failure output, and dispatches a new Claude Code worker to fix the issues

#### Scenario: Max retries exceeded
- **WHEN** eval fails and the retry count has reached the configured maximum (default: 3)
- **THEN** the system stops retrying, logs the failure context, and exits with an error indicating human intervention is needed

### Requirement: Agent self-tests behavior (best-effort, not a gate)
The system SHALL instruct the code agent to exercise the implemented feature and report what it tested and observed. Self-test output is captured but does NOT determine pass/fail — only the external eval gates progression.

#### Scenario: Self-test included in prompt
- **WHEN** the code agent is dispatched
- **THEN** the system prompt includes instructions to exercise the feature after implementation and report observations
