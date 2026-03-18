## ADDED Requirements

### Requirement: RunStats model
The system SHALL provide a `RunStats` Pydantic model in `reporting.py` with fields `passed: int`, `failed: int`, `total: int`, and `success_rate: float`.

#### Scenario: Model field values
- **WHEN** a `RunStats` is constructed with `passed=3`, `failed=2`, `total=5`, `success_rate=60.0`
- **THEN** all fields SHALL be accessible with those values

### Requirement: compute_run_stats function
The system SHALL provide a `compute_run_stats(manifests: list[RunManifest]) -> RunStats` function in `reporting.py` that computes success/failure counts and success rate from a list of run manifests.

#### Scenario: Stats from mixed manifests
- **WHEN** `compute_run_stats` is called with 5 manifests where 3 have `success=True` and 2 have `success=False`
- **THEN** the returned `RunStats` SHALL have `passed=3`, `failed=2`, `total=5`, `success_rate=60.0`

#### Scenario: Empty manifest list
- **WHEN** `compute_run_stats` is called with an empty list
- **THEN** the returned `RunStats` SHALL have `passed=0`, `failed=0`, `total=0`, `success_rate=0.0`

### Requirement: Lead uses shared stats
The `_gather_recent_runs` function in `lead.py` SHALL use `compute_run_stats` from `reporting.py` instead of computing success counts inline.

#### Scenario: Lead stats delegation
- **WHEN** `_gather_recent_runs` computes run statistics
- **THEN** it SHALL call `compute_run_stats` with its sliced manifest list and derive `(passed, total)` from the result

### Requirement: Report uses shared stats
The `aggregate_report` function in `reporting.py` SHALL use `compute_run_stats` instead of computing success/failure counts inline.

#### Scenario: Report stats delegation
- **WHEN** `aggregate_report` computes success/failure counts
- **THEN** it SHALL call `compute_run_stats` with the full manifest list and use the result for `total_runs`, `successful_runs`, `failed_runs`, and `success_rate`
