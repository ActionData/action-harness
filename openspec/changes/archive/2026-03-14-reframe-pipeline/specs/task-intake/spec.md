## ADDED Requirements

### Requirement: Accept task via CLI
The system SHALL accept an OpenSpec change name and repo path via CLI: `action-harness run --change <name> --repo <path>`. The `--repo` flag specifies the local path to the target repository. The system SHALL validate that `openspec/changes/<name>/` exists in the target repo before proceeding.

#### Scenario: Run with valid change
- **WHEN** the user runs `action-harness run --change add-logging --repo ./action-harness`
- **THEN** the system validates that `openspec/changes/add-logging/` exists and begins the implementation workflow

#### Scenario: Change does not exist
- **WHEN** the user runs `action-harness run --change nonexistent --repo ./action-harness`
- **THEN** the system exits with a clear error: change directory not found

#### Scenario: Repo path invalid
- **WHEN** the user runs `action-harness run --change foo --repo ./does-not-exist`
- **THEN** the system exits with a clear error: repo path not found

### Requirement: Validate required CLI tools
The system SHALL verify that `claude` and `gh` are available in PATH before proceeding. These are required for worker dispatch and PR creation respectively.

#### Scenario: Claude CLI not installed
- **WHEN** the user runs the harness but `claude` is not in PATH
- **THEN** the system exits with error: "claude CLI not found in PATH"

#### Scenario: gh CLI not installed
- **WHEN** the user runs the harness but `gh` is not in PATH
- **THEN** the system exits with error: "gh CLI not found in PATH"
