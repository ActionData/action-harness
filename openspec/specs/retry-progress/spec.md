# retry-progress Specification

## Purpose
TBD - created by archiving change retry-progress. Update Purpose after archive.
## Requirements
### Requirement: Progress file written after each worker dispatch
The harness SHALL write a `.harness-progress.md` file in the worktree after each worker dispatch + eval cycle. The file SHALL accumulate across retries (append, not overwrite).

#### Scenario: Progress file written after first dispatch
- **WHEN** the first worker dispatch completes and eval runs
- **THEN** `.harness-progress.md` SHALL be created in the worktree root with an "Attempt 1" section containing commits count, eval result (pass/fail), eval feedback (if failed), duration, and cost

#### Scenario: Progress file appended on retry
- **WHEN** a second worker dispatch completes after a retry
- **THEN** `.harness-progress.md` SHALL contain both "Attempt 1" and "Attempt 2" sections

#### Scenario: Progress file not written on first attempt success
- **WHEN** the first worker dispatch succeeds and eval passes (no retry needed)
- **THEN** the harness SHALL NOT write `.harness-progress.md` (no subsequent dispatch will read it)

#### Scenario: Progress file section format
- **WHEN** the progress file is written after attempt 1 with `WorkerResult(commits_ahead=3, cost_usd=0.23, duration_seconds=45.2)` and `EvalResult(success=False, feedback_prompt="ruff: unused import")`
- **THEN** the file SHALL contain a section starting with `## Attempt 1` followed by lines containing `3` (commits count), `FAILED` (eval result), the feedback text `ruff: unused import`, `45.2` (duration), and `0.23` (cost)

### Requirement: Progress file read by worker on retry dispatch
The harness SHALL include the contents of `.harness-progress.md` in the worker's user prompt when the file exists. The progress contents SHALL appear before the task/feedback content in the prompt.

#### Scenario: Retry dispatch includes progress
- **WHEN** a retry dispatch is made and `.harness-progress.md` exists
- **THEN** the user prompt SHALL contain the progress file contents before the eval feedback. The prompt order SHALL be: progress contents, then the base task prompt or eval feedback.

#### Scenario: First dispatch has no progress
- **WHEN** the first dispatch is made (no prior attempts)
- **THEN** the user prompt SHALL be unchanged (no progress file exists)

### Requirement: Harness writes the progress file, not the worker
The progress file SHALL be written by the harness's Python code (deterministic), not by the worker (LLM). The worker SHALL NOT modify the progress file.

#### Scenario: Progress file contains ground-truth data
- **WHEN** the progress file is written
- **THEN** it SHALL contain data from the harness's `WorkerResult` and `EvalResult` models (`commits_ahead`, `success`, `error`, `duration_seconds`, `cost_usd`) — not LLM-generated summaries

### Requirement: Progress file excluded from commits
The `.harness-progress.md` file SHALL NOT be committed to the repository. It is an operational artifact for the retry loop only.

#### Scenario: Progress file added to gitignore
- **WHEN** the harness writes `.harness-progress.md`
- **THEN** it SHALL be added to the worktree's `.gitignore`

### Requirement: Pre-work eval on retries
Before dispatching a retry worker, the harness SHALL run eval in the worktree. If eval passes (a prior commit fixed the issue), the harness SHALL skip the retry and proceed to PR creation.

#### Scenario: Pre-work eval passes on retry
- **WHEN** the harness is about to dispatch retry attempt N and pre-work eval passes
- **THEN** the harness SHALL skip the worker dispatch, set `eval_result` to the pre-work eval result, and proceed to PR creation using the prior iteration's `worker_result` for the `create_pr()` call

#### Scenario: Pre-work eval fails on retry
- **WHEN** the harness is about to dispatch retry attempt N and pre-work eval fails
- **THEN** the harness SHALL dispatch the retry worker with the pre-work eval's `feedback_prompt` from its `EvalResult` (not the stale feedback from the prior iteration)

#### Scenario: Pre-work eval not run on first dispatch
- **WHEN** the first worker dispatch is about to start
- **THEN** no pre-work eval SHALL be run (there's nothing to verify yet)

#### Scenario: Pre-work eval not run after worker failure with zero commits
- **WHEN** the harness retries after a worker failure that produced zero commits
- **THEN** the harness SHALL NOT run pre-work eval (the worktree is unchanged from the prior state)

