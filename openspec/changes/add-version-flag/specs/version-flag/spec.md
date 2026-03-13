## ADDED Requirements

### Requirement: CLI displays version
The CLI SHALL accept a `--version` flag that prints the package version and exits.

#### Scenario: Version flag prints version
- **WHEN** the user runs `action-harness --version`
- **THEN** the output contains the version string (e.g., "0.1.0") and the process exits with code 0
