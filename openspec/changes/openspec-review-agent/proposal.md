## Why

The harness pipeline currently ends at PR creation. There is no validation that the OpenSpec lifecycle was completed correctly — tasks checked off, delta specs well-formed, implementation matching spec intent. Without this, the spec system drifts from reality and archival becomes manual cleanup instead of a natural part of shipping.

The OpenSpec review agent is the final gate before merge. It validates spec correctness, performs semantic review (does the implementation match the spec?), archives completed task groups, and pushes those changes to the PR branch. This closes the loop: the harness ships code changes end-to-end with spec artifacts treated as part of the code.

## What Changes

- Add an OpenSpec review agent that runs as the final pipeline stage after PR creation
- The agent validates: tasks are checked off, delta specs are structurally correct (`openspec validate`), and the implementation semantically matches the spec
- When satisfied, the agent archives the completed change (`openspec archive`) and pushes the archive changes to the PR branch
- The agent can come back with questions/findings if the implementation has gaps relative to the spec
- The agent has access to `openspec` CLI, deepwiki (for OpenSpec documentation), and the repo's files

## Capabilities

### New Capabilities

- `openspec-review`: Pipeline stage that validates OpenSpec lifecycle completion — task checkoff, delta spec correctness, semantic spec-implementation alignment, and automated archival. Runs as the final gate before merge.

### Modified Capabilities

## Impact

- `src/action_harness/pipeline.py` — new stage after PR creation (or after code review agents when those exist)
- New module `src/action_harness/openspec_reviewer.py` — agent dispatch and result handling
- `src/action_harness/models.py` — new result type for OpenSpec review
- `openspec/ROADMAP.md` — add to Bootstrap section after `agent-debuggability`
