# cross-repo-openspec Specification

## Purpose
TBD - created by archiving change harness-dashboard. Update Purpose after archive.
## Requirements
### Requirement: Read OpenSpec changes from a repo

`read_openspec_changes(repo_path)` SHALL scan `<repo_path>/openspec/changes/` for active changes. For each change, it SHALL read `tasks.md` and count `- [x]` (complete) vs `- [ ]` (incomplete) lines to determine progress. Completed changes (in `openspec/changes/archive/`) SHALL be counted but not enumerated individually.

#### Scenario: Repo with active changes
- **WHEN** `openspec/changes/` contains directories `add-logging` and `fix-auth` (not in archive)
- **THEN** the function returns 2 `ChangeInfo` objects with progress percentages

#### Scenario: Task counting
- **WHEN** `openspec/changes/add-logging/tasks.md` contains 3 `- [x]` and 7 `- [ ]` lines
- **THEN** the `ChangeInfo` for `add-logging` has `tasks_complete=3`, `task_count=10`, `progress_pct=30.0`

#### Scenario: No tasks.md
- **WHEN** a change directory exists but has no `tasks.md`
- **THEN** the `ChangeInfo` has `task_count=0`, `tasks_complete=0`, `progress_pct=0.0`

#### Scenario: Completed changes counted
- **WHEN** `openspec/changes/archive/` contains 5 archived change directories
- **THEN** `completed_count` is 5

#### Scenario: Repo without OpenSpec
- **WHEN** `openspec/changes/` does not exist
- **THEN** the function returns an empty list and `completed_count=0`

### Requirement: Read roadmap from a repo

`read_roadmap(repo_path)` SHALL read `<repo_path>/openspec/ROADMAP.md` and return its content as a string, or None if the file does not exist.

#### Scenario: Roadmap exists
- **WHEN** `openspec/ROADMAP.md` exists
- **THEN** the function returns the file content as a string

#### Scenario: No roadmap
- **WHEN** `openspec/ROADMAP.md` does not exist
- **THEN** the function returns `None`

### Requirement: CLI roadmap command

`harness roadmap` SHALL print a cross-repo view showing each onboarded repo's roadmap summary and active OpenSpec changes with progress bars.

#### Scenario: Multiple repos with OpenSpec
- **WHEN** two repos are onboarded: `action-harness` with 2 active changes (one at 50%), `analytics-monorepo` with 1 active change (at 0%)
- **THEN** the output groups changes under repo name headers and shows progress bars, e.g., `action-harness` section contains `◉ review-tolerance  [██████████░░░░░░░░░░] 50%`

#### Scenario: Repo without OpenSpec
- **WHEN** a repo has no `openspec/` directory
- **THEN** it is listed with "No OpenSpec" indicator

#### Scenario: JSON output
- **WHEN** the user runs `harness roadmap --json`
- **THEN** the output is a JSON array of `RepoRoadmap` objects

### Requirement: RepoRoadmap model

`RepoRoadmap` SHALL contain: `repo_name` (str), `roadmap_content` (str or None), `active_changes` (list of `ChangeInfo`), and `completed_count` (int).

#### Scenario: Model fields
- **WHEN** a `RepoRoadmap` is constructed for a repo with a roadmap and 3 active changes
- **THEN** it contains the repo name, roadmap content string, list of 3 `ChangeInfo` objects, and the completed change count

