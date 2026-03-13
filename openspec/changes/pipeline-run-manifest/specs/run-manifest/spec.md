## ADDED Requirements

### Requirement: Pipeline produces a run manifest
The pipeline SHALL collect all stage results during execution and produce a `RunManifest` containing: change name, repo path, start/end timestamps, success status, ordered list of stage results, total duration, total cost, retry count, PR URL (if created), and error (if failed).

#### Scenario: Successful run produces manifest
- **WHEN** the pipeline completes successfully with PR created
- **THEN** the manifest contains all stage results in execution order, `success: true`, the PR URL, and total cost/duration

#### Scenario: Failed run produces manifest
- **WHEN** the pipeline fails at the eval stage with max_retries=2 (initial attempt + 2 re-attempts)
- **THEN** the manifest contains stage results up to and including the failure, `success: false`, `retries: 2` (counting re-attempts, not the initial attempt), and the error message

### Requirement: Manifest persisted to disk
The pipeline SHALL write the manifest as JSON to `.action-harness/runs/<ISO-timestamp>-<change-name>.json` in the repo directory. The manifest SHALL be written on both success and failure. The `.action-harness/` directory SHALL be created if it does not exist.

#### Scenario: Manifest file created on success
- **WHEN** the pipeline completes successfully
- **THEN** a JSON file exists at `.action-harness/runs/` containing the manifest data

#### Scenario: Manifest file created on failure
- **WHEN** the pipeline fails
- **THEN** a JSON file exists at `.action-harness/runs/` containing the manifest with failure details

#### Scenario: Directory created if missing
- **WHEN** the pipeline runs for the first time and `.action-harness/runs/` does not exist
- **THEN** the directory is created before writing the manifest

#### Scenario: Manifest filename follows convention
- **WHEN** the pipeline completes for change "test-feature"
- **THEN** the manifest filename matches the pattern `*-test-feature.json` in `.action-harness/runs/`

### Requirement: Manifest directory is gitignored
The `.action-harness/` directory SHALL be added to `.gitignore` so manifests are not committed to the repository.

#### Scenario: Gitignore includes action-harness directory
- **WHEN** `.gitignore` is read
- **THEN** it contains `.action-harness/`

### Requirement: Pipeline returns manifest to caller
The `run_pipeline` function SHALL return the `RunManifest` alongside the `PrResult` so downstream consumers (CLI, PR body builder, review agents) can access it without reading from disk.

#### Scenario: CLI receives manifest
- **WHEN** `run_pipeline` completes
- **THEN** the caller receives both the `PrResult` and the `RunManifest`

### Requirement: Manifest includes per-stage timing
Each stage result in the manifest SHALL include its duration. The manifest SHALL include total pipeline duration computed from start to end timestamps.

#### Scenario: Stage durations recorded
- **WHEN** the pipeline completes with 4 stages
- **THEN** each stage result in the manifest has a `duration_seconds` field and the manifest has `total_duration_seconds`
