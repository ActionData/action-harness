## Why

Review agents produce 15+ findings per round across 3 agents. The fix-retry worker receives ALL findings as feedback and addresses maybe 8-10, leaving 5-7 unresolved. Each fix introduces new code surface, and the next review round finds more issues. After 2 fix-retry rounds, 19 findings remained unresolved in the review-tolerance run.

The root cause: the worker is overwhelmed by volume. Sending 15 findings is like assigning 15 tasks at once — the agent loses focus and addresses the easy ones while deeper issues persist. Limiting the findings per retry and prioritizing by severity would let the worker focus on the most important issues first.

## What Changes

- Add `--max-findings-per-retry` flag (default 5) to cap how many findings are sent to the worker per fix-retry
- `format_review_feedback` selects the top N findings by severity (critical > high > medium > low), breaking ties by the number of agents that flagged the same issue
- Remaining findings below the cap are logged but not sent to the worker — they're addressed in the next review round
- The review cycle continues until all rounds are exhausted or no actionable findings remain

## Capabilities

### New Capabilities
- `focused-fix-retry`: Cap and prioritize review findings sent to the fix-retry worker. Configurable via `--max-findings-per-retry`.

### Modified Capabilities
None — this modifies the internal behavior of `format_review_feedback`, not its interface.

## Impact

- `review_agents.py` — `format_review_feedback` gains a `max_findings` parameter, selects top N by severity
- `cli.py` — new `--max-findings-per-retry` flag
- `pipeline.py` — thread the parameter through to fix-retry dispatch
- `models.py` — no changes (findings are already structured)
