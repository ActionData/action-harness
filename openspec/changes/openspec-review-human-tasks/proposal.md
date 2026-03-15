## Why

The openspec-review agent marks the pipeline as `failed` when tasks tagged `[HUMAN]` are incomplete. These are tasks the agent literally cannot do (verify API tokens, watch CI run, merge to master). The pipeline did everything it could — implemented code, passed eval, opened PR, ran reviews. Reporting this as failure is misleading and prevents the PR from being flagged as ready for human action.

## What Changes

- Add a `needs-human` pipeline status for when all agent-completable work is done but human tasks remain
- Teach the openspec-review agent to recognize `[HUMAN]` tagged tasks as expected-incomplete
- When only `[HUMAN]` tasks remain: don't archive (change isn't fully done), don't report failure, report `needs-human`
- The pipeline returns success with a `needs_human` flag so the PR can be labeled accordingly

## Capabilities

### New Capabilities

- `human-task-awareness`: OpenSpec review agent recognizes `[HUMAN]` tagged tasks as expected-incomplete and reports `needs-human` status instead of failure.

### Modified Capabilities

## Impact

- `src/action_harness/openspec_reviewer.py` — update system prompt to recognize `[HUMAN]` tags
- `src/action_harness/pipeline.py` — handle `needs-human` status from review agent
- `src/action_harness/models.py` — add `needs_human` field to result models
