## Why

When `harness lead --repo .` starts an interactive session without a user prompt, the LLM must process the entire system prompt context (roadmap, issues, assessment scores, recent runs, ready changes) and generate a greeting from scratch. This is slow (the agent spends its first turn parsing context) and inconsistent (different sessions produce different greeting formats).

The gathered context is already structured data. The harness should build a concise greeting summary from it and pass it as the initial message, so the agent starts with pre-formatted context and can respond immediately with a focused, consistent greeting.

## What Changes

- Add a `build_greeting` function in `lead.py` that takes the gathered context sections and produces a formatted greeting prompt
- When no user prompt is provided in interactive mode, pass the built greeting as the initial message instead of relying on the agent to synthesize one from system prompt alone
- The greeting includes: repo name, active change status, recent run outcomes, ready changes, and suggested directions

## Capabilities

### New Capabilities

- `build_greeting`: Deterministic greeting builder that formats gathered context into a concise initial prompt for the lead agent

### Modified Capabilities

- `dispatch_lead_interactive`: When no user prompt is provided, uses the built greeting as the initial message
- `gather_lead_context`: Returns structured sections (not just a flat string) so the greeting builder can use them selectively

## Impact

- `src/action_harness/lead.py` — add `build_greeting`, modify `gather_lead_context` to return structured data alongside flat context
- `src/action_harness/cli.py` — pass greeting to `dispatch_lead_interactive` when no user prompt
- `tests/test_lead.py` — test greeting builder
