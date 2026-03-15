## Why

The harness currently requires a change name or prompt passed via CLI. To dispatch work from a GitHub issue, the operator must manually read the issue, extract the task, and run `harness run --change <name>` or `harness run --prompt "..."`. This is a manual bottleneck that prevents event-driven operation.

GitHub issues are a natural intake channel. An issue labeled `harness` or referencing an OpenSpec change should be dispatchable directly: `harness run --issue 42 --repo owner/repo`. The harness reads the issue, determines whether it maps to an existing OpenSpec change or is a freeform task, and dispatches accordingly.

## What Changes

- New `--issue` flag on `harness run` that accepts a GitHub issue number
- The harness reads the issue via `gh issue view` and extracts the task
- If the issue body references an OpenSpec change (e.g., `openspec:change-name`), use `--change` mode
- Otherwise, use `--prompt` mode with the issue title + body as the prompt
- The PR links back to the issue (`Closes #42`) for automatic issue closure on merge
- Issue is labeled with harness status (`harness:in-progress`, `harness:pr-created`)

## Capabilities

### New Capabilities
- `github-issue-intake`: Read GitHub issues via `gh issue view`, extract task description, detect OpenSpec change references, dispatch as change or prompt mode, link PR to issue.

### Modified Capabilities
None

## Impact

- `cli.py` — add `--issue` flag to `run` command, mutually exclusive with `--change` and `--prompt`
- New module `issue_intake.py` — issue reading, OpenSpec reference detection, prompt extraction
- `pr.py` — PR body includes `Closes #<issue>` when dispatched from an issue
- `pipeline.py` — pass issue metadata through for PR linking
## Prerequisites

Requires `unspecced-tasks` to be implemented first (roadmap item 4). The `--prompt` fallback for issues without an OpenSpec change reference uses `slugify_prompt()` and the prompt-mode worker dispatch, both introduced by `unspecced-tasks`. Without it, only issues referencing an existing OpenSpec change can be dispatched.
