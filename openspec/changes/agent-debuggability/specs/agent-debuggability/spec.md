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
Every pipeline stage SHALL return a result object (dataclass or Pydantic model) that includes at minimum: `success` (bool), `stage` (str), and an optional `error` (str). Stages SHALL NOT communicate outcomes solely through exceptions. Exceptions are reserved for unexpected errors (bugs), not expected failures (eval fails, no commits).

#### Scenario: Eval failure returns result object
- **WHEN** an eval command fails
- **THEN** the evaluator returns a result with `success=False`, `stage="eval"`, and `error` containing the failure details

#### Scenario: Successful worker dispatch returns result object
- **WHEN** a worker dispatch completes and produces commits
- **THEN** the worker returns a result with `success=True`, `stage="worker"`, and relevant metadata (cost, duration)

### Requirement: Pipeline stages are independently callable
Every pipeline stage SHALL be a standalone function with explicit typed parameters. Stages SHALL NOT depend on global state or require prior stages to have run (except for their explicit inputs). Any stage can be called directly in a test or debugging session.

#### Scenario: Evaluator called without prior worker dispatch
- **WHEN** an agent calls `run_eval(worktree_path)` directly on a worktree that already has code changes
- **THEN** the evaluator runs all eval commands and returns a result, without requiring the worker to have been dispatched by the pipeline

#### Scenario: Worktree creation called independently
- **WHEN** an agent calls `create_worktree(change_name, repo_path)` directly
- **THEN** a worktree is created and a result object is returned, without requiring CLI validation to have run first

### Requirement: Verbose mode provides detailed diagnostics
The CLI SHALL accept a `--verbose` flag. When enabled, stderr output SHALL include: full subprocess commands being executed, working directories, and output previews (first 20 lines of subprocess output). Default mode logs only stage boundaries.

#### Scenario: Default mode output is concise
- **WHEN** the harness runs without `--verbose`
- **THEN** stderr contains only stage entry/exit lines (approximately 2 lines per stage)

#### Scenario: Verbose mode shows subprocess details
- **WHEN** the harness runs with `--verbose`
- **THEN** stderr includes the full command line for each subprocess invocation, the working directory, and a preview of the output

### Requirement: Dry-run mode validates without executing
The CLI SHALL accept a `--dry-run` flag. When enabled, the harness SHALL validate all inputs, resolve paths, and print the planned execution sequence to stdout, then exit without creating worktrees, dispatching workers, running eval, or creating PRs.

#### Scenario: Dry-run with valid inputs
- **WHEN** the harness runs with `--dry-run --change add-logging --repo .`
- **THEN** the harness prints the planned stages (worktree path, worker command, eval commands, PR title) and exits with code 0

#### Scenario: Dry-run with invalid inputs
- **WHEN** the harness runs with `--dry-run --change nonexistent --repo .`
- **THEN** the harness exits with an error (same as normal mode) because validation still runs

### Requirement: CLAUDE.md documents agent-debuggability rules
CLAUDE.md SHALL include design rules requiring: (1) every I/O function logs to stderr and returns structured results, (2) pipeline stages are independently callable, (3) no fire-and-forget operations. These rules apply to all bootstrap and self-hosted code.

#### Scenario: New pipeline module follows rules
- **WHEN** a new pipeline module is implemented
- **THEN** it includes stderr logging at stage boundaries, returns result objects, and can be called independently — as enforced by the CLAUDE.md rules and verified by review agents
