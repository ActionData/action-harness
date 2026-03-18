# project-layout Specification

## Purpose
Per-repo project directory structure that consolidates all harness state — clone, workspaces, run history, catalog knowledge, and config — into a single self-contained directory at `$HARNESS_HOME/projects/<repo-name>/`.

## Requirements
### Requirement: Project directory structure

Each managed repo SHALL have a self-contained project directory at `$HARNESS_HOME/projects/<repo-name>/` containing subdirectories: `repo/` (git clone), `workspaces/` (worktrees), `runs/` (manifests), `knowledge/` (catalog data), and a `config.yaml` file.

#### Scenario: New repo onboarded
- **WHEN** the operator runs `harness run --change foo --repo owner/my-app` for the first time
- **THEN** the harness creates `$HARNESS_HOME/projects/my-app/` with subdirectories `repo/`, `workspaces/`, `runs/`, `knowledge/` and a `config.yaml` file
- **AND** the repo is cloned into `$HARNESS_HOME/projects/my-app/repo/`

#### Scenario: Project directory already exists
- **WHEN** the operator runs against a repo that was previously onboarded
- **THEN** the harness reuses the existing project directory without re-creating it

#### Scenario: Removing a project
- **WHEN** the operator deletes `$HARNESS_HOME/projects/my-app/`
- **THEN** all harness state for that repo (clone, workspaces, runs, knowledge, config) is removed

### Requirement: Project config file

Each project SHALL have a `config.yaml` at `$HARNESS_HOME/projects/<repo-name>/config.yaml`. It SHALL be created on first onboard with `repo_name` and `remote_url` fields.

#### Scenario: Config created on first onboard
- **WHEN** a repo is cloned for the first time via `--repo owner/my-app`
- **THEN** `config.yaml` is created with `repo_name: my-app` and `remote_url` set to the clone URL

#### Scenario: Config exists on subsequent runs
- **WHEN** the harness runs against an already-onboarded repo
- **THEN** `config.yaml` is read but not overwritten

#### Scenario: Config identifies managed project
- **WHEN** listing onboarded repos (e.g., `harness repos`)
- **THEN** a directory under `projects/` is considered a managed project if `config.yaml` exists

#### Scenario: Directory without config is not listed
- **WHEN** a directory exists under `$HARNESS_HOME/projects/` without a `config.yaml` (e.g., half-created from a failed clone)
- **THEN** `harness repos` does NOT list it as a managed project

### Requirement: Centralized run manifests

Run manifests SHALL be written to `$HARNESS_HOME/projects/<repo-name>/runs/<run-id>.json` instead of inside the worktree. Manifests SHALL persist after workspace cleanup.

#### Scenario: Manifest written to project runs directory
- **WHEN** a pipeline run completes for repo `my-app`
- **THEN** the manifest is written to `$HARNESS_HOME/projects/my-app/runs/<run-id>.json`

#### Scenario: Manifest survives workspace cleanup
- **WHEN** a workspace is cleaned via `harness clean`
- **THEN** the run manifests in `projects/my-app/runs/` are NOT deleted

#### Scenario: Report reads from project runs directory
- **WHEN** `harness report --repo my-app` is run
- **THEN** it reads manifests from `$HARNESS_HOME/projects/my-app/runs/`

### Requirement: Local repos bypass project layout

When `--repo` is a local path (`.`, `/abs/path`), the harness SHALL NOT create a project directory. Worktrees SHALL use `/tmp/` as before. The project layout only applies to managed repos (cloned via `owner/repo` or URL).

#### Scenario: Local repo uses temp worktree
- **WHEN** the operator runs `harness run --change foo --repo .`
- **THEN** the worktree is created in `/tmp/action-harness-*/` (existing behavior)
- **AND** no project directory is created under `$HARNESS_HOME/projects/`

#### Scenario: Local repo manifests stay in worktree
- **WHEN** a pipeline run completes for a local repo
- **THEN** the manifest is written to `<worktree>/.action-harness/runs/<run-id>.json` (existing behavior)
