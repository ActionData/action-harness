## ADDED Requirements

### Requirement: Load protected path patterns from config
The pipeline SHALL read protected file patterns from `.harness/protected-paths.yml` in the target repo. The file SHALL contain a `protected` key with a list of glob pattern strings.

#### Scenario: Config file exists with patterns
- **WHEN** the repo contains `.harness/protected-paths.yml` with patterns `["src/action_harness/pipeline.py", "CLAUDE.md"]`
- **THEN** the pipeline loads both patterns for matching

#### Scenario: Config file missing
- **WHEN** the repo does not contain `.harness/protected-paths.yml`
- **THEN** the pipeline treats all files as unprotected and logs a note to stderr

#### Scenario: Config file malformed
- **WHEN** `.harness/protected-paths.yml` exists but is invalid YAML or missing the `protected` key
- **THEN** the pipeline logs a warning to stderr and treats all files as unprotected

### Requirement: Check diff against protected patterns
The pipeline SHALL compare the list of changed files (from `git diff --name-only`) against the protected patterns using glob matching. Any file matching a protected pattern SHALL be flagged.

#### Scenario: Protected file modified
- **WHEN** the diff includes `src/action_harness/pipeline.py` and `pipeline.py` is a protected pattern
- **THEN** the file is flagged as protected

#### Scenario: No protected files modified
- **WHEN** the diff includes only `src/action_harness/new_module.py` and no pattern matches it
- **THEN** no files are flagged as protected

#### Scenario: Glob pattern matching
- **WHEN** the protected pattern is `src/action_harness/*.py` and the diff includes `src/action_harness/worker.py`
- **THEN** the file is flagged as protected

### Requirement: Flag PR when protected files are modified
When protected files are detected, the pipeline SHALL post a PR comment listing the protected files and add a `protected-paths` label to the PR via `gh pr edit --add-label`.

#### Scenario: PR flagged with comment and label
- **WHEN** the protection check finds `pipeline.py` and `CLAUDE.md` as protected
- **THEN** a PR comment is posted listing both files, and the `protected-paths` label is added

#### Scenario: No protected files — no flag
- **WHEN** the protection check finds no protected files
- **THEN** no comment is posted and no label is added

### Requirement: Protection check runs after PR creation
The protection check SHALL run after the PR is created but before review agents dispatch. This allows review agents to see the protection flag.

#### Scenario: Check ordering in pipeline
- **WHEN** the pipeline reaches the protection check stage
- **THEN** it runs after `create_pr` succeeds and before `_run_review_agents`

### Requirement: Protection result in manifest
The `RunManifest` SHALL include a `protected_files` field (list of strings) listing any protected files that were modified. An empty list means no protected files were touched.

#### Scenario: Manifest includes protected files
- **WHEN** the pipeline completes and `pipeline.py` was flagged as protected
- **THEN** `manifest.protected_files` contains `"src/action_harness/pipeline.py"`

#### Scenario: Manifest with no protected files
- **WHEN** no protected files were detected
- **THEN** `manifest.protected_files` is an empty list

### Requirement: Default protected paths for this repo
The harness repo SHALL ship with a `.harness/protected-paths.yml` containing default protected patterns for its own critical files.

#### Scenario: Default config present
- **WHEN** the action-harness repo is checked
- **THEN** `.harness/protected-paths.yml` exists with patterns covering at minimum `pipeline.py`, `evaluator.py`, and `cli.py`
