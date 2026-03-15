## ADDED Requirements

### Requirement: Baseline eval before worker dispatch
The pipeline SHALL run eval commands in the worktree before the worker is dispatched. The results SHALL be recorded as the baseline.

#### Scenario: Baseline recorded
- **WHEN** the worktree is created and before the worker runs
- **THEN** all eval commands are run and their pass/fail status is recorded

### Requirement: Post-worker eval compares against baseline
After the worker completes, eval SHALL compare each command's result against the baseline. Only regressions (passing → failing) SHALL cause eval failure.

#### Scenario: Regression detected
- **WHEN** `uv run ruff check .` passed at baseline but fails after the worker's changes
- **THEN** eval reports a regression failure for that command

#### Scenario: Pre-existing failure ignored
- **WHEN** `uv run ruff format --check .` failed at baseline and still fails after changes
- **THEN** eval does NOT report this as a failure — it's noted as pre-existing

#### Scenario: Worker fixed pre-existing issue
- **WHEN** `uv run pytest -v` failed at baseline but passes after changes
- **THEN** eval notes this as a fix and does not fail

### Requirement: Baseline results in manifest
The `RunManifest` SHALL include baseline eval results showing which commands passed and which failed before the worker started.

#### Scenario: Manifest includes baseline
- **WHEN** the pipeline completes
- **THEN** the manifest contains `baseline_eval` with per-command pass/fail status
