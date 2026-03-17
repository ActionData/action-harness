## ADDED Requirements

### Requirement: Report command aggregates run manifests
The `harness report --repo <path>` command SHALL read all `RunManifest` JSON files from `.action-harness/runs/` and produce an aggregate report.

#### Scenario: Report with multiple runs
- **WHEN** the repo has 5 run manifests (3 successful, 2 failed)
- **THEN** the report SHALL show success rate as `3/5 (60%)`, list the failure stages, and show total/average cost and duration

#### Scenario: No runs
- **WHEN** the repo has no run manifests
- **THEN** the command SHALL output "No runs found" and exit cleanly

### Requirement: Report shows failure stage distribution
The report SHALL count and display which pipeline stages caused failures, ordered by frequency.

#### Scenario: Multiple failures at different stages
- **WHEN** 2 runs failed at eval and 1 failed at review
- **THEN** the report SHALL show `eval: 2 failures` before `review: 1 failure`

### Requirement: Report shows recurring review findings
The report SHALL group review findings across runs by title similarity and show the most frequent ones.

#### Scenario: Same finding in multiple runs
- **WHEN** 3 runs each have a finding titled "subprocess.run missing timeout" (or similar substring)
- **THEN** the report SHALL group them and show the count as 3

### Requirement: Report includes catalog rule frequency
The report SHALL read the per-repo knowledge store and display catalog rule hit counts.

#### Scenario: Catalog frequency data exists
- **WHEN** `findings-frequency.json` has entries with counts
- **THEN** the report SHALL display the top entries sorted by count descending

#### Scenario: No frequency data
- **WHEN** no `findings-frequency.json` exists
- **THEN** the catalog section SHALL be omitted (no error)

### Requirement: --since filter limits report scope
The `--since` flag SHALL filter manifests by `started_at` timestamp.

#### Scenario: Filter by relative duration
- **WHEN** the user runs `harness report --repo . --since 7d`
- **THEN** only manifests with `started_at` within the last 7 days SHALL be included

#### Scenario: Filter by absolute date
- **WHEN** the user runs `harness report --repo . --since 2026-03-15`
- **THEN** only manifests with `started_at` on or after 2026-03-15 SHALL be included

### Requirement: --json outputs machine-readable report
The `--json` flag SHALL output the full report as a JSON object to stdout. All diagnostic output SHALL go to stderr.

#### Scenario: JSON output
- **WHEN** the user runs `harness report --repo . --json`
- **THEN** stdout SHALL contain valid JSON with keys: `success_rate`, `total_runs`, `failures_by_stage`, `recurring_findings`, `catalog_frequency`, `total_cost_usd`, `avg_duration_seconds`
