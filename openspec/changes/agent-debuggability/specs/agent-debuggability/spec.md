## ADDED Requirements

### Requirement: Pipeline stages log to stderr at stage boundaries
Every pipeline stage (validate, create_worktree, dispatch_worker, run_eval, create_pr) SHALL print a log line to stderr when entering and exiting the stage. Entry lines SHALL include the stage name and key inputs. Exit lines SHALL include the stage name and outcome (success/failure).

#### Scenario: Successful pipeline run produces stderr timeline
- **WHEN** the harness runs a pipeline to completion
- **THEN** stderr contains one entry and one exit line per stage, in execution order, showing inputs and outcomes

#### Scenario: Failed pipeline run shows where failure occurred
- **WHEN** the harness fails at the eval stage
- **THEN** stderr shows entry/exit lines for all stages up to and including eval, with the eval exit line indicating failure

### Requirement: Pipeline stages return typed result objects
Every pipeline stage SHALL return a Pydantic model that includes at minimum: `success` (bool), `stage` (str), and an optional `error` (str). Stages SHALL NOT communicate outcomes solely through exceptions. Exceptions are reserved for unexpected errors (bugs), not expected failures (eval fails, no commits).

#### Scenario: Eval failure returns result object
- **WHEN** an eval command fails
- **THEN** the evaluator returns a result with `success=False`, `stage="eval"`, and `error` containing the failure details

#### Scenario: Successful worker dispatch returns result object
- **WHEN** a worker dispatch completes and produces commits
- **THEN** the worker returns a result with `success=True`, `stage="worker"`, and relevant metadata (cost, duration)

### Requirement: Pipeline stages are independently callable
Every pipeline stage SHALL be a standalone function with explicit typed parameters. Stages SHALL NOT depend on global state or require prior stages to have run (except for their explicit inputs). The `verbose` flag SHALL be passed as an explicit `verbose: bool` parameter, not stored as module-level or global state.

#### Scenario: Evaluator called without prior worker dispatch
- **WHEN** a test calls `run_eval(worktree_path, eval_commands)` directly on a worktree that already has code changes
- **THEN** `run_eval` returns an `EvalResult` without the test needing to instantiate a pipeline or call any other stage function

#### Scenario: Worktree creation called independently
- **WHEN** a test calls `create_worktree(change_name, repo_path)` directly
- **THEN** `create_worktree` returns a `WorktreeResult` without the test needing to call `validate_inputs` or any CLI function first

### Requirement: Verbose mode provides detailed diagnostics
The CLI SHALL accept a `--verbose` flag. The flag SHALL be passed as an explicit parameter to pipeline stage functions. When enabled, stderr output SHALL include: full subprocess commands being executed, working directories, and output previews (first 20 lines of subprocess output). Default mode logs only stage boundaries.

#### Scenario: Default mode output is concise
- **WHEN** the harness runs without `--verbose`
- **THEN** stderr contains only stage entry/exit lines (approximately 2 lines per stage)

#### Scenario: Verbose mode shows subprocess details
- **WHEN** the harness runs with `--verbose`
- **THEN** stderr includes the full command line for each subprocess invocation, the working directory, and a preview of the output

### Requirement: Dry-run mode validates without executing
The CLI SHALL accept a `--dry-run` flag. When enabled, the harness SHALL validate all inputs, resolve paths, and print the planned execution sequence to stdout (the plan is the final output of a dry-run), then exit without creating worktrees, dispatching workers, running eval, or creating PRs. When both `--verbose` and `--dry-run` are passed, behavior SHALL be identical to `--dry-run` alone.

#### Scenario: Dry-run with valid inputs
- **WHEN** the harness runs with `--dry-run --change add-logging --repo .`
- **THEN** stdout contains the planned stages (worktree path, eval commands, change name) and the harness exits with code 0

#### Scenario: Dry-run with invalid inputs
- **WHEN** the harness runs with `--dry-run --change nonexistent --repo .`
- **THEN** the harness exits with an error (same as normal mode) because validation still runs

#### Scenario: Dry-run with verbose has no additional effect
- **WHEN** the harness runs with `--dry-run --verbose --change add-logging --repo .`
- **THEN** the output is identical to `--dry-run` alone because no subprocesses are executed

### Requirement: CLAUDE.md documents agent-debuggability rules
CLAUDE.md SHALL include design rules requiring: (1) every I/O function logs to stderr and returns structured results, (2) pipeline stages are independently callable with explicit typed parameters, (3) no fire-and-forget operations. These rules apply to all bootstrap and self-hosted code.

#### Scenario: CLAUDE.md contains agent-debuggability rules
- **WHEN** CLAUDE.md is read
- **THEN** it contains sections covering agent-debuggability and logging conventions under the design rules
