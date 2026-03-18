## Why

Run statistics (success counts, pass rates, recent run lists) are computed independently in `lead.py` (`_gather_recent_runs`) and `reporting.py` (`aggregate_report`). They use different window sizes (5 vs 10), different sort strategies, and different data models (`tuple[int, int]` vs `RunReport`). This makes behavior inconsistent and maintenance harder — any change to stats logic requires coordinated edits in two modules.

## What Changes

- Extract a shared `compute_run_stats` function in `reporting.py` that computes success/failure counts over a configurable window of recent manifests.
- Refactor `_gather_recent_runs` in `lead.py` to call the shared function instead of computing stats inline.
- Refactor `aggregate_report` in `reporting.py` to call the shared function for its success/failure counting.
- Align the recent-run window size: both callers use a `limit` parameter with their own defaults (5 for lead, 10 for report).

## Capabilities

### New Capabilities

- `shared-run-stats`: A reusable function for computing success/failure counts and recent run summaries from a list of manifests, with configurable window size.

### Modified Capabilities

## Impact

- `src/action_harness/reporting.py` — new shared function, refactored `aggregate_report`
- `src/action_harness/lead.py` — refactored `_gather_recent_runs` to use shared function
- `tests/test_reporting.py` — new tests for shared function
- `tests/test_lead.py` — updated tests if signatures change
