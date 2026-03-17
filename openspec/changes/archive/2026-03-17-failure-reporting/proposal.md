## Why

The harness produces run manifests and event logs per pipeline run, but there's no way to see patterns across runs. After 10+ runs, questions like "which review findings keep recurring?", "what's the most common failure stage?", and "which catalog rules fire most often?" require manually reading JSON files.

Failure reporting aggregates data across runs into a summary that reveals systemic patterns — the kind of insight that feeds back into the knowledge catalog and helps prioritize what to fix.

## What Changes

- New CLI command: `harness report --repo <path>` that reads all run manifests and produces an aggregate report
- Report includes: success/failure rate, most common failure stages, most frequent review findings, catalog rule hit frequency, cost/duration trends
- `--json` flag for machine-readable output
- `--since <date>` filter for time-bounded reports
- Reads from `.action-harness/runs/*.json` (existing manifests) and per-repo knowledge store

## Capabilities

### New Capabilities
- `failure-reporting`: Aggregate run manifests into a summary report with success rates, failure patterns, recurring review findings, and catalog rule frequency.

### Modified Capabilities
None

## Impact

- `cli.py` — new `report` command
- New module `src/action_harness/reporting.py` — manifest aggregation and report generation
- Reads existing `.action-harness/runs/*.json` manifests (no schema changes needed)
- Reads `~/.harness/repos/<repo>/knowledge/findings-frequency.json` from the catalog
- No changes to pipeline, worker, or review agents
