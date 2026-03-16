# assessment-report Specification

## Purpose
TBD - created by archiving change codebase-assessment. Update Purpose after archive.
## Requirements
### Requirement: AssessmentReport model with per-category scores
The assessment SHALL produce an `AssessmentReport` Pydantic model with an overall score, per-category scores, and identified gaps.

#### Scenario: Complete report structure
- **WHEN** an assessment completes in any mode
- **THEN** the `AssessmentReport` SHALL contain `overall_score` (int 0-100), `categories` (dict mapping category name to `CategoryScore`), `proposals` (list of gaps), `repo_path`, `timestamp`, and `mode`

#### Scenario: CategoryScore structure
- **WHEN** a category is scored
- **THEN** the `CategoryScore` SHALL contain `score` (int 0-100), `mechanical_signals` (a typed model specific to the category, e.g., `CIMechanicalSignals` for ci_guardrails), `agent_assessment` (str or None), and `gaps` (list of `Gap`)

#### Scenario: Gap structure
- **WHEN** a gap is identified
- **THEN** the `Gap` SHALL contain `severity` (high/medium/low), `finding` (str), `category` (str), and `proposal_name` (str or None, kebab-case)

### Requirement: Overall score is the average of category scores
The `overall_score` SHALL be the arithmetic mean of all six category scores, rounded to the nearest integer.

#### Scenario: All categories scored
- **WHEN** categories score [80, 60, 90, 20, 80, 100]
- **THEN** the overall score SHALL be 72

### Requirement: Report renders to terminal
The assessment report SHALL be printed to the terminal in a human-readable format showing per-category scores with visual bars, findings, and gap summaries.

#### Scenario: Terminal output for base scan
- **WHEN** `harness assess --repo ./path` completes
- **THEN** the output SHALL include all six category names, their numeric scores (0-100), and the overall score

#### Scenario: Terminal output for deep scan
- **WHEN** `harness assess --repo ./path --deep` completes
- **THEN** the output SHALL additionally include agent assessment rationale text for each category

### Requirement: Report serializable to JSON
The `AssessmentReport` SHALL be serializable to JSON via `.model_dump_json()` for persistence and comparison over time.

#### Scenario: JSON roundtrip preserves all fields
- **WHEN** an `AssessmentReport` with categories containing gaps with `proposal_name` values is serialized via `model_dump_json()` and deserialized via `model_validate_json()`
- **THEN** all fields SHALL survive the roundtrip: `categories["ci_guardrails"].gaps[0].proposal_name` SHALL equal the original value, `categories["ci_guardrails"].score` SHALL equal the original integer, and `overall_score` SHALL equal the original value

### Requirement: JSON output mode via --json flag
When the `--json` flag is provided, the CLI SHALL output the full `AssessmentReport` JSON to stdout. All diagnostic and progress output SHALL go to stderr.

#### Scenario: --json outputs to stdout
- **WHEN** the user runs `harness assess --repo ./path --json`
- **THEN** stdout SHALL contain valid JSON parseable as an `AssessmentReport` and stderr SHALL contain any diagnostic messages

#### Scenario: --json without --deep
- **WHEN** the user runs `harness assess --repo ./path --json` without `--deep`
- **THEN** the JSON output SHALL have `mode: "base"` and all `agent_assessment` fields SHALL be null

### Requirement: Six scoring categories
The assessment SHALL score exactly six categories: context, testability, ci_guardrails, observability, tooling, and isolation.

#### Scenario: All categories present
- **WHEN** an assessment completes
- **THEN** the `categories` dict SHALL contain exactly the keys: `context`, `testability`, `ci_guardrails`, `observability`, `tooling`, `isolation`

#### Scenario: Base mode scores from mechanical signals only
- **WHEN** the assessment runs without `--deep`
- **THEN** all `agent_assessment` fields SHALL be None and scores SHALL be derived from mechanical signals only

