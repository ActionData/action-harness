## Why

The harness dispatches autonomous workers that run end-to-end without human interaction — from code change through eval, retry, and PR creation. These workers need repo-specific guidance that doesn't belong in CLAUDE.md (which targets interactive sessions) or AGENTS.md (which describes agent capabilities). Things like which skills to invoke, extra eval steps, paths to avoid, retry hints for flaky tests, and context about ongoing migrations are critical for autonomous success but have no home today.

Without this, every repo the harness works on gets the same generic treatment regardless of its quirks, and repo-specific knowledge stays in the operator's head instead of being codified.

## What Changes

- Define a `HARNESS.md` file convention that lives in the target repo root
- The harness reads `HARNESS.md` at worker dispatch time and injects its contents into the worker's system prompt
- `HARNESS.md` is optional — repos without one work exactly as they do today
- Document the convention: what belongs in HARNESS.md vs CLAUDE.md vs AGENTS.md

## Capabilities

### New Capabilities
- `harness-md`: Convention, discovery, parsing, and injection of per-repo HARNESS.md files into autonomous worker prompts

### Modified Capabilities

Note: The roadmap lists `workspace-management` as a prerequisite for multi-repo use. This change works without it — it reads from whatever worktree path is provided. Multi-repo workspace management is additive.

## Impact

- `worker.py` — prompt construction must check for and include HARNESS.md content
- `onboard.py` / repo profiling — deferred to the `repo-profiling` change. When that lands, it should detect HARNESS.md presence and surface it in the repo profile. This change does not modify onboarding.
- Worker system prompt template — needs a slot for HARNESS.md content
- Documentation — CLAUDE.md should document the HARNESS.md convention and when to use it
