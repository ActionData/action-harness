# Review Agents Specification

## Overview

The review-agents capability dispatches independent Claude Code workers to review a PR for bugs, test gaps, and quality issues. Findings are triaged by severity. High-severity findings trigger a fix-retry cycle before proceeding to the OpenSpec review stage.

## Requirements

### REQ-RA-001: Review Agent Dispatch

The pipeline SHALL dispatch three review agents after successful PR creation: bug-hunter, test-reviewer, and quality-reviewer. Each agent SHALL be a separate Claude Code CLI invocation using `claude -p` with `--output-format json`.

#### Scenario: All three agents dispatched after PR creation
- WHEN the pipeline creates a PR successfully
- THEN the pipeline dispatches exactly three Claude Code CLI processes: one for bug-hunter, one for test-reviewer, one for quality-reviewer
- AND each process receives the PR number and repository context

#### Scenario: Review agents are skipped when PR creation fails
- WHEN PR creation returns `success=False`
- THEN no review agents are dispatched

### REQ-RA-002: Parallel Execution

Review agents SHALL be dispatched concurrently, not sequentially. The pipeline SHALL wait for all three to complete before proceeding to triage.

#### Scenario: Agents run concurrently
- WHEN the pipeline dispatches review agents
- THEN all three `claude` CLI processes are started before any completes
- AND the pipeline waits for all three to finish

#### Scenario: One agent failure does not block others
- WHEN one review agent process exits with a nonzero return code
- THEN the other two agents continue to completion
- AND the failed agent's result is recorded with `success=False`

### REQ-RA-003: PR Diff as Input

Each review agent SHALL receive the PR diff via `gh pr diff {pr_number}` as context. Agents SHALL run with `cwd` set to the worktree for CLI context (e.g., `gh` needs a git repo) but SHALL NOT modify any files. They are read-only reviewers.

#### Scenario: Agent receives PR diff
- WHEN a review agent is dispatched
- THEN its system prompt instructs it to run `gh pr diff` to obtain the changes
- AND its system prompt instructs it to read full files for context as needed

#### Scenario: Agent does not modify files
- WHEN a review agent completes
- THEN no files in the worktree or repository have been modified by the agent

### REQ-RA-004: Structured Finding Output

Each review agent SHALL produce a JSON output block containing a list of findings. Each finding SHALL have: `title` (string), `file` (string), `line` (int or null), `severity` (one of "critical", "high", "medium", "low"), and `description` (string).

#### Scenario: Agent produces valid findings JSON
- WHEN a review agent completes successfully
- THEN its output contains a JSON block with key `findings` whose value is a list
- AND each finding in the list has keys: `title`, `file`, `line`, `severity`, `description`

#### Scenario: Agent finds no issues
- WHEN a review agent completes and finds no issues
- THEN its output contains `{"findings": [], "summary": "..."}`

#### Scenario: Agent output cannot be parsed
- WHEN the review agent's output does not contain a valid JSON block
- THEN the pipeline records a `ReviewResult` with `success=False` and `error` describing the parse failure
- AND the pipeline treats the agent as having produced zero findings

### REQ-RA-005: ReviewResult Model

The pipeline SHALL use a `ReviewResult` model for each agent's result. The model SHALL include: `stage` (literal "review"), `agent_name` (string), `success` (bool), `error` (string or null), `duration_seconds` (float or null), `findings` (list of `ReviewFinding`), and `cost_usd` (float or null).

#### Scenario: ReviewResult recorded in manifest
- WHEN a review agent completes
- THEN a `ReviewResult` is appended to the manifest's `stages` list
- AND the `ReviewResult` contains the agent name, duration, findings, and cost

### REQ-RA-006: ReviewFinding Model

Each finding SHALL be represented as a `ReviewFinding` model with fields: `title` (str), `file` (str), `line` (int or null), `severity` (literal "critical" | "high" | "medium" | "low"), `description` (str), and `agent` (str, the name of the agent that produced it).

#### Scenario: Finding has all required fields
- WHEN a finding is parsed from agent output
- THEN the `ReviewFinding` instance has non-empty `title`, `file`, `severity`, `description`, and `agent` fields

### REQ-RA-007: Severity-Based Triage

After all agents complete, the pipeline SHALL triage findings by severity. If any finding has severity "critical" or "high", the pipeline SHALL re-dispatch the code worker with the findings as structured feedback.

#### Scenario: High-severity findings trigger fix retry
- WHEN review agents produce at least one finding with severity "critical" or "high"
- THEN the pipeline re-dispatches the code worker with the findings formatted as feedback
- AND the pipeline re-runs eval after the fix attempt
- AND the pipeline updates the PR with new commits

#### Scenario: Only medium/low findings do not trigger retry
- WHEN all review findings have severity "medium" or "low"
- THEN the pipeline proceeds directly to OpenSpec review without re-dispatching the worker

#### Scenario: No findings proceed to OpenSpec review
- WHEN review agents produce zero findings
- THEN the pipeline proceeds directly to OpenSpec review

### REQ-RA-008: Fix Retry Limit

The review-triggered fix retry SHALL be limited to one attempt. If the fix retry fails eval or produces new high-severity findings, the pipeline SHALL proceed to OpenSpec review with the findings recorded but no further retry.

#### Scenario: Fix retry succeeds
- WHEN the fix worker completes and eval passes
- THEN the pipeline proceeds to OpenSpec review

#### Scenario: Fix retry fails eval
- WHEN the fix worker completes but eval fails
- THEN the pipeline records the failure
- AND the pipeline proceeds to OpenSpec review (does not retry again)

#### Scenario: Fix retry produces new high-severity findings
- WHEN the fix retry is complete and review agents are NOT re-run
- THEN the pipeline proceeds to OpenSpec review (single retry only)

### REQ-RA-009: Review Summary in PR Body

After review agents complete, the pipeline SHALL post a PR comment summarizing findings from each reviewer. The comment SHALL group findings by agent and include severity, title, file, and line for each finding.

#### Scenario: PR comment posted with findings
- WHEN review agents produce findings
- THEN a comment is posted on the PR via `gh pr comment` containing the findings summary

#### Scenario: PR comment posted with clean result
- WHEN review agents produce zero findings across all three agents
- THEN a comment is posted on the PR indicating all reviews passed with no findings

### REQ-RA-010: Agent System Prompts

Each review agent SHALL use a system prompt based on the agent definitions in `~/.claude/agents/` (bug-hunter.md, test-reviewer.md, quality-reviewer.md), extended with instructions to produce structured JSON output. Prompts are hardcoded in the module (point-in-time copy, not read at runtime). The user prompt SHALL include the PR number.

#### Scenario: Bug-hunter prompt matches agent definition
- WHEN the bug-hunter agent is dispatched
- THEN its system prompt contains the bug-hunting instructions from the agent definition
- AND its system prompt includes instructions to output a JSON block with `findings` key

#### Scenario: Agent prompt includes PR number
- WHEN any review agent is dispatched
- THEN its user prompt includes the PR number so the agent can run `gh pr diff {number}`

### REQ-RA-011: Pipeline Stage Ordering

The review-agents stage SHALL run after PR creation and before OpenSpec review. The full pipeline order SHALL be: worktree -> worker -> eval -> PR -> review-agents -> triage -> (optional fix retry -> eval -> PR update) -> openspec-review.

#### Scenario: Review agents run before OpenSpec review
- WHEN the pipeline completes successfully
- THEN the manifest stages show review agent results appearing before the OpenSpec review result

#### Scenario: Fix retry inserts before OpenSpec review
- WHEN a fix retry is triggered
- THEN the additional worker and eval results appear in the manifest after the review results and before the OpenSpec review result

### REQ-RA-012: StageResultUnion Update

The `StageResultUnion` discriminated union in `models.py` SHALL include `ReviewResult` so that review results are properly serialized and deserialized in the manifest.

#### Scenario: ReviewResult round-trips through JSON
- WHEN a `RunManifest` containing `ReviewResult` stages is serialized to JSON and deserialized back
- THEN the `ReviewResult` instances are preserved with correct types and field values
