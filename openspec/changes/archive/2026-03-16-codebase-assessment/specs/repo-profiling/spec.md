## ADDED Requirements

### Requirement: Profiler exposes ecosystem for assessment consumption
The existing `profile_repo()` function and `RepoProfile` model SHALL remain unchanged. The assessment scanner SHALL call `profile_repo()` to obtain ecosystem and eval_commands, then perform its own additional scanning. The assessment does not modify `RepoProfile`.

#### Scenario: Assessment uses existing profiler
- **WHEN** the assessment scanner runs on a repository
- **THEN** it SHALL call `profile_repo()` to obtain the `RepoProfile` and use `ecosystem` and `marker_file` fields as input signals for category scoring
