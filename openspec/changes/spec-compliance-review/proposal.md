## Why

The implementing worker marks tasks as `[x]` but sometimes doesn't actually do what the task describes. In the review-tolerance run, task 4.4 said "call match_findings" — the worker implemented the function and tested it but never called it in the pipeline. The task was marked complete. The eval gate (pytest/ruff/mypy) can't catch semantic compliance — it only verifies syntax, types, and test assertions.

A spec compliance reviewer would compare each completed task against the actual diff and flag discrepancies: "Task says to call match_findings, but the diff shows match_findings is never imported in pipeline.py."

## What Changes

- New review agent: `spec-compliance-reviewer` that runs alongside bug-hunter, test-reviewer, and quality-reviewer
- The agent receives: the tasks.md file, the git diff, and instructions to verify each `[x]` task was actually implemented as described
- Findings are structured like other review findings (severity, file, description)
- Integrated into the existing review dispatch — no new pipeline stages

## Capabilities

### New Capabilities
- `spec-compliance-review`: A review agent that compares completed task descriptions against the implementation diff to catch tasks marked done but not actually implemented.

### Modified Capabilities
None — this adds a new agent to the existing review dispatch, not a new stage.

## Impact

- `review_agents.py` — add spec-compliance-reviewer to the agent list and prompt builder
- `pipeline.py` — the existing `dispatch_review_agents` already dispatches all configured agents. Adding a new agent type requires no pipeline changes if the dispatch is data-driven.
- Works on any repo using OpenSpec — the agent reads tasks.md (standard artifact) and the diff (always available)
