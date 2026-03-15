## Why

The review agent triage currently only triggers a fix-retry for high/critical severity findings. Medium and low findings are posted as a PR comment and ignored. This is not acceptable — the harness should hold the highest standards for code quality.

On the first external repo run (analytics-monorepo hex-guides), a medium bug (workflow publishing on all PRs instead of just master merges) and several low findings (missing tests, glob pattern mismatch) were posted as comments but never fixed by the worker. The PR shipped with known issues that the harness identified but didn't address.

## What Changes

- Change triage logic: fix ALL actionable findings, not just high/critical
- The worker fix-retry should address high, critical, medium, and substantive low findings
- Only skip truly advisory items (style opinions, hypothetical future concerns, "consider this")
- Add severity thresholds to the triage function: `fix` (high/critical/medium + actionable low), `note` (advisory low), `skip` (style only)
- The fix-retry feedback should include all findings to fix, not just the high/critical subset

## Capabilities

### New Capabilities

- `strict-review-triage`: Stricter triage that addresses all actionable findings, not just high/critical. Only truly advisory items are noted without action.

### Modified Capabilities

## Impact

- `src/action_harness/review_agents.py` — update `triage_findings` logic and `format_review_feedback`
- `src/action_harness/pipeline.py` — update `_run_review_fix_retry` trigger condition
- `tests/test_review_agents.py` — update triage tests for new thresholds
- `tests/test_pipeline_review.py` — update integration tests
