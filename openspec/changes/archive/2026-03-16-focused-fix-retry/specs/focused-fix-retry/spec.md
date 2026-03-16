## ADDED Requirements

### Requirement: Cap findings sent to fix-retry worker
The `format_review_feedback` function SHALL accept a `max_findings: int` parameter that limits how many findings are included in the feedback text. Default: 5.

#### Scenario: More findings than cap
- **WHEN** there are 12 actionable findings and `max_findings=5`
- **THEN** the feedback text SHALL contain exactly 5 findings, selected by priority (highest severity first)

#### Scenario: Fewer findings than cap
- **WHEN** there are 3 actionable findings and `max_findings=5`
- **THEN** the feedback text SHALL contain all 3 findings (cap not reached)

#### Scenario: Cap of zero means no limit
- **WHEN** `max_findings=0`
- **THEN** the feedback text SHALL contain all actionable findings (backward compatible)

### Requirement: Findings prioritized by severity and cross-agent agreement
Findings SHALL be sorted by priority score: `SEVERITY_RANK[severity] * 10 + cross_agent_count`, where `cross_agent_count` is the number of distinct agents that flagged a finding on the same file with overlapping title text (case-insensitive substring match).

#### Scenario: Critical finding always outranks medium
- **WHEN** one critical finding has `cross_agent_count=1` and one medium finding has `cross_agent_count=3`
- **THEN** the critical finding SHALL rank higher (score 30+1=31 vs 10+3=13)

#### Scenario: Same severity, more agents ranks higher
- **WHEN** two high-severity findings exist, one flagged by 3 agents and one by 1 agent
- **THEN** the 3-agent finding SHALL rank higher (score 20+3=23 vs 20+1=21)

#### Scenario: Cross-agent detection with title overlap
- **WHEN** bug-hunter flags "null check missing in handler" on `foo.py` and quality-reviewer flags "Missing null check" on `foo.py`
- **THEN** `cross_agent_count` for both SHALL be 2 (same file, "null check" is a substring of both titles)

#### Scenario: Cross-agent detection without title overlap
- **WHEN** bug-hunter flags "race condition" on `foo.py` and quality-reviewer flags "unused import" on `foo.py`
- **THEN** `cross_agent_count` for both SHALL be 1 (same file but no title substring overlap — different issues)

### Requirement: Deferred findings logged but not lost
Findings below the cap SHALL be logged to stderr and remain in the `ReviewResult` stages for the manifest. They are NOT removed from the data — just excluded from the worker feedback text.

#### Scenario: Deferred findings logged
- **WHEN** 12 findings exist and cap is 5
- **THEN** stderr SHALL include a message like "[review] deferred 7 finding(s) below priority cap"

#### Scenario: Deferred findings in manifest
- **WHEN** findings are deferred
- **THEN** the `RunManifest` stages SHALL still contain ALL `ReviewResult` entries with ALL findings (not just the top N)

### Requirement: CLI flag for max findings per retry
The `harness run` command SHALL accept `--max-findings-per-retry` (int, default 5) to configure the findings cap.

#### Scenario: Custom cap
- **WHEN** the user runs with `--max-findings-per-retry 3`
- **THEN** fix-retry feedback SHALL contain at most 3 findings

#### Scenario: Default cap
- **WHEN** the user runs without `--max-findings-per-retry`
- **THEN** the default cap of 5 SHALL be used

#### Scenario: Dry-run shows cap
- **WHEN** the user runs with `--dry-run --max-findings-per-retry 3`
- **THEN** the dry-run output SHALL show `max-findings-per-retry: 3`
