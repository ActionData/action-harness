## Context

Run manifests are already written at `.action-harness/runs/<run-id>.json` with full stage results, timing, cost, and success/failure status. The knowledge catalog frequency store tracks per-entry hit counts at `~/.harness/repos/<repo>/knowledge/findings-frequency.json`. All the raw data exists — this change adds aggregation and presentation.

## Goals / Non-Goals

**Goals:**
- `harness report --repo <path>` CLI command
- Aggregate across all manifests (or filtered by `--since`)
- Success/failure rate by change name
- Most common failure stages (worktree, worker, eval, PR, review)
- Top recurring review findings (by title similarity, grouped across runs)
- Catalog rule frequency from the knowledge store
- Cost and duration trends (average, total)
- `--json` for machine-readable output
- Human-readable terminal output with summary stats

**Non-Goals:**
- Real-time monitoring (that's `live-progress-feed`)
- Alerting or notifications (that's `always-on`)
- Modifying manifests or frequency data (read-only aggregation)
- Cross-repo aggregation (single repo at a time)

## Decisions

### 1. Read existing manifests, don't add new data collection

All data comes from existing sources:
- `RunManifest` JSON files in `.action-harness/runs/`
- `findings-frequency.json` from the catalog knowledge store
- No new data collection points in the pipeline

### 2. Report sections

```
Harness Report — owner/repo
Period: last 30 days (12 runs)

Success Rate:  10/12 (83%)
Total Cost:    $14.23
Avg Duration:  32m

Top Failure Stages:
  eval:    2 failures
  review:  1 failure (fix-retry exhausted)

Top Recurring Findings:
  "subprocess.run missing timeout" — 4 runs
  "bare assert for type narrowing"  — 3 runs

Catalog Rule Frequency:
  subprocess-timeout:  count=8
  bare-assert:         count=4
  type-ignore-ban:     count=3

Recent Runs:
  2026-03-16 checkpoint-resume  ✓  $1.23  45m
  2026-03-16 agent-definitions  ✗  $0.89  22m (review failed)
  2026-03-15 focused-fix-retry  ✓  $1.45  38m
```

### 3. Finding similarity for cross-run grouping

Review findings from different runs are grouped by title similarity (case-insensitive substring match — same as `_titles_overlap`). This surfaces findings that keep appearing across runs, indicating systemic issues.

### 4. `--since` filter

Default: all runs. `--since 7d` (last 7 days), `--since 2026-03-15` (since date). Filters manifests by `started_at` timestamp.

### 5. `--json` output

Full report as a JSON object to stdout. Diagnostic output to stderr. Same pattern as `harness assess --json`.

## Risks / Trade-offs

- [Many manifests] A repo with hundreds of runs could be slow to aggregate → Mitigation: `--since` filter limits the scope. Manifests are small JSON files.
- [Finding grouping quality] Substring matching may over-group or under-group findings → Mitigation: same matching logic used elsewhere. Good enough for surfacing patterns.
