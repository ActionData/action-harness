## Context

The openspec-review agent's system prompt (openspec_reviewer.py) instructs it to verify all tasks are `[x]`. When tasks tagged `[HUMAN]` are incomplete, the agent reports findings and the pipeline returns `failed`. But `[HUMAN]` tasks are intentionally agent-incomplete — they require human action (verify API tokens, watch CI, merge to master).

The pipeline did everything it could. Reporting `failed` is misleading.

## Goals / Non-Goals

**Goals:**
- Teach the openspec-review agent to distinguish `[HUMAN]` tasks from regular tasks
- Add `needs-human` as a third outcome alongside `approved` and `findings`
- Pipeline reports success with a `needs_human` flag when only human tasks remain
- PR gets a label/comment indicating human action needed

**Non-Goals:**
- Parsing `[HUMAN]` tags in the harness code (the LLM agent reads the tasks and understands the tag)
- Auto-completing human tasks
- Changing the `[HUMAN]` tag convention

## Decisions

### 1. `needs-human` status in agent output JSON

Add `needs-human` as a valid `status` value in the review agent's JSON output. The agent outputs this when all regular tasks are `[x]` but `[HUMAN]` tasks remain `[ ]`.

```json
{
  "status": "needs-human",
  "tasks_total": 10,
  "tasks_complete": 7,
  "human_tasks_remaining": 3,
  "validation_passed": true,
  "semantic_review_passed": true,
  "findings": ["3 human tasks remaining: ..."],
  "archived": false
}
```

**Why:** Clean third state. The agent distinguishes "I found problems" (findings) from "I'm done, humans aren't" (needs-human).

### 2. System prompt update — recognize `[HUMAN]` tag

Update the openspec-review system prompt to instruct: when checking tasks.md, tasks with `[HUMAN]` in the task text are expected to be incomplete. Count them separately. If all non-HUMAN tasks are `[x]` and only HUMAN tasks remain `[ ]`, report `needs-human` instead of `findings`. Do NOT archive (the change isn't fully complete).

**Why:** The agent needs explicit instruction to handle this convention. Without it, any incomplete task is a finding.

### 3. Pipeline treats `needs-human` as success with a flag

When the openspec-review returns `needs-human`, the pipeline:
- Reports success (exit code 0)
- Sets `needs_human=True` on the manifest
- Posts a PR comment listing the remaining human tasks
- Adds a `needs-human` label to the PR

**Why:** The harness did its job. The PR is ready for human action, not a redo.

## Risks / Trade-offs

**[Risk] Task authors forget to tag human tasks with `[HUMAN]`.**
→ Mitigation: The convention is documented. If a task is untagged and incomplete, the agent correctly reports it as a finding.

**[Trade-off] No archival on `needs-human`.**
→ Correct. Archival means the change is fully done. Human tasks still pending means it's not.
