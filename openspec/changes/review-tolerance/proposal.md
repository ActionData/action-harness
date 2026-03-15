## Why

The review cycle is currently hardcoded: 2 rounds of review → fix-retry, every finding at every severity triggers a fix. This creates two problems. First, the harness spends equal effort on low-severity style nits and critical bugs — expensive when each fix-retry is a full Claude Code dispatch. Second, findings the worker declines to fix disappear silently — subsequent review rounds re-flag the same concern because there's no trail, and humans reviewing the PR can't tell if a finding was considered or ignored.

Configurable tolerance levels let operators tune review depth to the task. An acknowledgment protocol ensures every finding gets a response — fix it or explain why not — with escalation to code comments when multiple reviewers flag the same non-issue.

## What Changes

- Add tolerance levels (`low`, `med`, `high`) that control which finding severities are actionable per review round. `low` = all severities, `med` = medium+, `high` = critical/high only.
- Replace the hardcoded 2-round review loop with a configurable review cycle — an ordered list of tolerance levels (default: `[low, med, high]`).
- Add `--review-cycle` CLI flag accepting a comma-separated list of tolerance levels (e.g., `--review-cycle low,med,high` or `--review-cycle high`).
- Require the fix-retry worker to address every actionable finding: fix in code, or post a PR comment explaining why not.
- Track acknowledged-but-not-fixed findings across rounds. When a second reviewer flags the same concern that was previously acknowledged, escalate to a code comment (two strikes = trap for future readers).
- Review agents still report all findings regardless of tolerance. Tolerance only filters which findings are sent to the fix-retry worker. All findings are posted to the PR comment for visibility.
- Short-circuit: if a review round produces zero actionable findings, skip remaining rounds.

## Capabilities

### New Capabilities
- `review-tolerance`: Tolerance-based filtering of review findings, configurable review cycle definition, and the acknowledgment/escalation protocol for declined findings.

### Modified Capabilities
- `review-agents`: Triage changes from binary (any findings → fix) to tolerance-aware filtering. Fix-retry loop changes from hardcoded 2 rounds to configurable cycle. Worker feedback format changes to include prior acknowledged findings and acknowledgment instructions.
- `strict-review-triage`: The "triage triggers on any findings" rule is superseded by tolerance-based triage. The spec's requirement that all findings trigger fix-retry is replaced by tolerance filtering.

## Impact

- `src/action_harness/review_agents.py` — `triage_findings()` gains a tolerance parameter; `format_review_feedback()` gains prior-acknowledged-findings section and acknowledgment instructions.
- `src/action_harness/pipeline.py` — Review loop changes from `range(2)` to iterating over the review cycle list. Needs to track acknowledged findings across rounds.
- `src/action_harness/models.py` — Adds `AcknowledgedFinding` model for tracking findings acknowledged but not fixed across rounds.
- `src/action_harness/cli.py` — New `--review-cycle` flag.
- Worker system prompt — Instructions for the acknowledgment protocol (fix or explain, PR comment for declines, code comment on second-flag escalation).
