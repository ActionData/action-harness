## Context

Run statistics are currently computed in two places:

1. **`lead.py::_gather_recent_runs`** — loads manifests, takes last 5, counts successes inline, formats a markdown section and returns `(section_text, (passed, total))`.
2. **`reporting.py::aggregate_report`** — takes all manifests, counts successes inline, computes failure stage distribution, cost/duration aggregation, and builds a `RunReport` with last 10 recent runs sorted by timestamp.

Both compute `sum(1 for m in manifests if m.success)` independently. The lead path uses a simple slice (`manifests[-5:]`) while the report path sorts by `started_at` timestamp. This is the core duplication.

## Goals / Non-Goals

**Goals:**
- Single function for computing success/failure counts from a list of manifests
- Both `_gather_recent_runs` and `aggregate_report` delegate to this shared function
- Callers pre-slice manifests before passing to the shared function

**Non-Goals:**
- Unifying the data models (`LeadContext.recent_run_stats` remains `tuple[int, int]`, `RunReport` keeps its full structure)
- Changing the report's additional aggregations (cost, duration, failure stages, recurring findings)
- Changing CLI output or formatting
- Changing the lead's manifest loading strategy (no `since` filter)

## Decisions

**1. Add `compute_run_stats` to `reporting.py`**

A new function `compute_run_stats(manifests)` returns a `RunStats` Pydantic model with `passed`, `failed`, `total`, and `success_rate`. Lives in `reporting.py` because that module already owns manifest loading and aggregation. The `RunStats` model itself lives in `models.py`, consistent with all other Pydantic data models in the codebase.

Alternative considered: separate `stats.py` module. Rejected — the function is small and `reporting.py` is the natural home for manifest-derived calculations.

**2. Use a Pydantic model for `RunStats`**

Consistent with the rest of the codebase (`RunReport`, `RecentRunSummary`, etc.). A simple model with `passed: int`, `failed: int`, `total: int`, `success_rate: float`.

**3. Callers pass pre-sliced manifests**

`compute_run_stats` operates on whatever list it receives. The caller is responsible for slicing/sorting. This keeps the function simple and avoids embedding window-size policy. The lead slices to 5, the report passes all manifests.

Alternative considered: `compute_run_stats` takes `limit` and slices internally. Rejected — the report needs stats over *all* manifests, not a windowed subset.

## Risks / Trade-offs

- [Low risk] Signature change to internal functions — both `_gather_recent_runs` and `aggregate_report` are internal, not part of the CLI API. Tests will need updating but no external consumers.
- [Low risk] Lead's `manifests[-5:]` slice doesn't sort by timestamp like the report does. This is existing behavior and not changed by this refactor — the lead's ordering comes from filesystem read order which is already chronological.
