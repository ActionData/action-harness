## Why

Per-repo state is scattered across two top-level directories: `~/harness/repos/<name>/` (git clone + catalog knowledge) and `~/harness/workspaces/<name>/` (worktrees). Run manifests live inside worktrees. There's no per-repo config or settings outside of what's checked into the target repo itself.

The repo-lead needs a single, self-contained directory per repo to read from — repo state, workspaces, run history, config, catalog data. The dashboard needs the same for its data layer. As the harness adds per-repo configurability (review cycle settings, lead context, agent overrides), that state needs a home that isn't inside the target repo's git tree.

Consolidating to `~/harness/projects/<name>/` gives each onboarded repo a single directory containing everything the harness knows about it. This is a prerequisite for repo-lead, and sets up the extensibility point for future per-repo configuration.

## What Changes

- Restructure the harness home layout from `repos/` + `workspaces/` to a unified `projects/<name>/` directory per repo
- Each project directory contains: `repo/` (git clone), `workspaces/` (worktrees), `runs/` (manifests), `knowledge/` (catalog frequency), and `config.yaml` (harness-level repo settings, initially minimal)
- Update all path construction in `repo.py`, `pipeline.py`, `cli.py`, `dashboard.py`, `branch_protection.py` to use the new layout
- Update `clean` command to work with the new structure
- No migration of old layout — fresh start
- Run manifests written to `projects/<name>/runs/` instead of inside the worktree's `.action-harness/` directory

## Capabilities

### New Capabilities
- `project-layout`: Per-repo project directory structure at `$HARNESS_HOME/projects/<name>/` containing repo clone, workspaces, run history, catalog knowledge, and config.

### Modified Capabilities
- `workspace-management`: All path references change from `repos/<name>` and `workspaces/<name>/<change>` to `projects/<name>/repo` and `projects/<name>/workspaces/<change>`. Clean command updated accordingly.

## Impact

- `src/action_harness/repo.py` — clone destination changes from `harness_home / "repos" / name` to `harness_home / "projects" / name / "repo"`
- `src/action_harness/pipeline.py` — workspace path changes from `harness_home / "workspaces" / name / change` to `harness_home / "projects" / name / "workspaces" / change`. Manifest output path changes to `projects/<name>/runs/`.
- `src/action_harness/cli.py` — all `repos/` and `workspaces/` path references updated. Clean command paths updated.
- `src/action_harness/dashboard.py` — scan `projects/` instead of `repos/` + `workspaces/` separately.
- `src/action_harness/branch_protection.py` — repo path reference updated if applicable.
- `config.yaml` created as empty/minimal on first repo onboard. Initial fields: `repo_name`, `remote_url`. Future: review cycle, lead settings, agent overrides.
