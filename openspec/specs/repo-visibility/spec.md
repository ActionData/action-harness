# repo-visibility Specification

## Purpose
TBD - created by archiving change harness-dashboard. Update Purpose after archive.
## Requirements
### Requirement: List onboarded repos

`list_repos(harness_home)` SHALL scan `<harness_home>/repos/` and return a `RepoSummary` for each subdirectory. Each summary SHALL include: repo name, path, remote URL (from `git remote get-url origin`), whether HARNESS.md exists, whether `.harness/protected-paths.yml` exists, workspace count, and OpenSpec active/completed change counts.

#### Scenario: Two repos onboarded
- **WHEN** `~/harness/repos/` contains directories `foo` and `bar`
- **THEN** `list_repos` returns a list of 2 `RepoSummary` objects with names `foo` and `bar`

#### Scenario: No repos onboarded
- **WHEN** `~/harness/repos/` is empty or does not exist
- **THEN** `list_repos` returns an empty list

#### Scenario: Repo has HARNESS.md
- **WHEN** `~/harness/repos/foo/HARNESS.md` exists
- **THEN** the `RepoSummary` for `foo` has `has_harness_md=True`

#### Scenario: Repo without protected paths
- **WHEN** `~/harness/repos/foo/.harness/protected-paths.yml` does not exist
- **THEN** the `RepoSummary` for `foo` has `has_protected_paths=False`

#### Scenario: Stale workspace count included
- **WHEN** `~/harness/workspaces/foo/` contains 3 workspace directories, 1 of which is stale
- **THEN** the `RepoSummary` for `foo` has `workspace_count=3` and `stale_workspace_count=1`

#### Scenario: Directory is not a git repo
- **WHEN** a directory under `~/harness/repos/` is not a git repository (no `.git`)
- **THEN** it is skipped and not included in the returned list

### Requirement: Repo detail view

`repo_detail(harness_home, repo_name)` SHALL return a `RepoDetail` for the named repo containing: the `RepoSummary`, HARNESS.md content (or None), protected path patterns, workspaces with staleness, roadmap content (or None), and OpenSpec change list with progress.

#### Scenario: Repo with HARNESS.md
- **WHEN** `~/harness/repos/foo/HARNESS.md` exists with content
- **THEN** `repo_detail` returns `harness_md_content` with the file contents

#### Scenario: Repo without HARNESS.md
- **WHEN** `~/harness/repos/foo/HARNESS.md` does not exist
- **THEN** `repo_detail` returns `harness_md_content=None`

#### Scenario: Repo with protected paths config
- **WHEN** `~/harness/repos/foo/.harness/protected-paths.yml` exists with patterns
- **THEN** `repo_detail` returns the list of glob patterns in `protected_patterns`

#### Scenario: Repo without OpenSpec
- **WHEN** `~/harness/repos/foo/openspec/` does not exist
- **THEN** `repo_detail` returns `roadmap_content=None` and `openspec_changes=[]`

### Requirement: CLI repos list command

`harness repos` SHALL print a formatted summary of all onboarded repos showing name, HARNESS.md presence, protected paths presence, workspace count, and OpenSpec change counts.

#### Scenario: Formatted output
- **WHEN** the user runs `harness repos` with repos `analytics-monorepo` (has HARNESS.md, no protected paths, 2 workspaces, 3 active changes) and `action-harness` (has both, 1 workspace, 4 active changes)
- **THEN** the output contains lines matching: `analytics-monorepo    HARNESS.md: ✓  Protected: ✗  Workspaces: 2  Changes: 3 active` and `action-harness        HARNESS.md: ✓  Protected: ✓  Workspaces: 1  Changes: 4 active`

#### Scenario: JSON output
- **WHEN** the user runs `harness repos --json`
- **THEN** the output is a JSON array of `RepoSummary` objects

### Requirement: CLI repos show command

`harness repos show <name>` SHALL print the detailed view of a single repo including HARNESS.md content, protected patterns, workspaces, roadmap, and OpenSpec changes.

#### Scenario: Repo exists
- **WHEN** the user runs `harness repos show foo` and `foo` is onboarded
- **THEN** the output shows the full detail view

#### Scenario: Repo not found
- **WHEN** the user runs `harness repos show nonexistent`
- **THEN** the CLI exits with an error: "Repo 'nonexistent' not found in <harness_home>/repos/"

#### Scenario: JSON output
- **WHEN** the user runs `harness repos show foo --json`
- **THEN** the output is a JSON `RepoDetail` object

