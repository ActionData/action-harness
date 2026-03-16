## ADDED Requirements

### Requirement: Catalog entries stored as YAML files
The catalog SHALL store entries as individual YAML files in `src/action_harness/catalog/entries/`. Each entry SHALL have: `id` (str), `class` (str), `severity` (high/medium/low), `ecosystems` (list of str), `worker_rule` (str), `reviewer_checklist` (list of str).

#### Scenario: Valid entry loaded
- **WHEN** `entries/subprocess-timeout.yaml` exists with valid fields
- **THEN** the loader SHALL return a catalog entry with `id="subprocess-timeout"`, `severity="high"`, `ecosystems=["python"]`

#### Scenario: Malformed YAML entry skipped with warning
- **WHEN** an entry file contains invalid YAML or is missing required fields
- **THEN** the loader SHALL skip it, log a warning to stderr, and continue loading remaining entries

#### Scenario: Entry with ecosystem "all"
- **WHEN** an entry has `ecosystems: [all]`
- **THEN** it SHALL be included for any ecosystem

### Requirement: Catalog loader filters by ecosystem
The `load_catalog(ecosystem: str)` function SHALL return only entries where the detected ecosystem is in the entry's `ecosystems` list OR the entry has `"all"` in its ecosystems.

#### Scenario: Python repo gets Python entries
- **WHEN** the ecosystem is "python"
- **THEN** the loader SHALL return entries with `ecosystems` containing "python" or "all", and exclude entries for "javascript", "rust", etc.

#### Scenario: Unknown ecosystem gets only universal entries
- **WHEN** the ecosystem is "unknown"
- **THEN** the loader SHALL return only entries with `ecosystems` containing "all"

### Requirement: Renderer produces worker rules (concise)
The `render_for_worker(top_n: int = 10)` method SHALL return a string with the top N entries by severity, formatted as a concise bulleted list of `worker_rule` values.

#### Scenario: Top 10 worker rules
- **WHEN** the catalog has 15 entries and `top_n=10`
- **THEN** the output SHALL contain exactly 10 rules, sorted by severity (high first), each on its own line

#### Scenario: Fewer entries than top_n
- **WHEN** the catalog has 3 entries and `top_n=10`
- **THEN** the output SHALL contain all 3 rules

#### Scenario: No entries returns None
- **WHEN** the catalog has 0 entries for the detected ecosystem
- **THEN** `render_for_worker` SHALL return None (caller skips injection)

### Requirement: Renderer produces reviewer checklist (detailed)
The `render_for_reviewer()` method SHALL return a string with all entries, formatted with `reviewer_checklist` items and `examples` for each entry.

#### Scenario: Full checklist
- **WHEN** the catalog has 10 entries
- **THEN** the output SHALL contain all 10 entries with their checklist items and example code

### Requirement: Worker rules injected into worker system prompt
The catalog worker rules SHALL be appended to the worker's system prompt at dispatch time, after HARNESS.md content.

#### Scenario: Worker prompt includes catalog rules
- **WHEN** a worker is dispatched on a Python repo with the catalog loaded
- **THEN** the system prompt SHALL contain a `## Quality Rules` section with the top N worker rules from the catalog

#### Scenario: No catalog entries for ecosystem
- **WHEN** the repo's ecosystem has no matching catalog entries
- **THEN** the worker prompt SHALL have no `## Quality Rules` section (no empty section injected)

### Requirement: Reviewer checklist injected into review agent prompts
The catalog reviewer checklist SHALL be appended to each review agent's system prompt.

#### Scenario: Review agent prompt includes checklist
- **WHEN** a review agent is dispatched on a Python repo
- **THEN** its system prompt SHALL contain a `## Catalog Checklist` section with the full reviewer checklist

### Requirement: Per-repo finding frequency tracking
After all review rounds complete (once per pipeline run, not per round), the harness SHALL classify review findings from all rounds against catalog entries and update a per-repo frequency file at `~/.harness/repos/<repo>/knowledge/findings-frequency.json`.

#### Scenario: Frequency incremented
- **WHEN** a review finding matches catalog entry `subprocess-timeout` (by keyword matching in finding title/description)
- **THEN** the frequency file SHALL increment the count for `subprocess-timeout` and update `last_seen`

#### Scenario: Frequency file created on first match
- **WHEN** no frequency file exists and a finding matches a catalog entry
- **THEN** the file SHALL be created with the matching entry's count set to 1

#### Scenario: High-frequency entries boosted in worker rules
- **WHEN** a repo has `subprocess-timeout` with count >= 3 and it's not already in the top N by severity
- **THEN** the worker rules SHALL include it as a boosted entry (up to 2 extra slots beyond top_n)
