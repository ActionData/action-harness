## Why

The harness manages repos, workspaces, and OpenSpec changes across multiple codebases, but there's no way to see the state of everything from one place. To check what repos are onboarded, which workspaces are active or stale, or what OpenSpec changes are in flight across repos, you have to manually navigate directories and run commands in each repo. As the number of onboarded repos grows, this becomes a real friction point for the operator.

A read-only data layer and CLI commands give immediate visibility. Building it as a structured API (functions returning Pydantic models) means a TUI or web dashboard can be layered on later without rework.

## What Changes

- New `harness repos` command — lists all onboarded repos with summary (HARNESS.md presence, protected paths, workspace count, OpenSpec change counts)
- New `harness repos show <name>` command — deep view of a single repo: HARNESS.md content, protected path patterns, workspaces with staleness, OpenSpec roadmap, and active/completed changes with progress
- New `harness workspaces` command — lists all workspaces across all repos with staleness detection (no commits in N days + no open PR)
- New `harness roadmap` command — cross-repo view of OpenSpec roadmaps and active changes
- New data layer module with functions returning Pydantic models — presentation-agnostic, consumable by CLI, future TUI, or web API
- All commands are read-only. No mutations, no subprocess dispatches.

## Capabilities

### New Capabilities
- `repo-visibility`: Data layer for reading repo state (summary, detail, HARNESS.md, protected paths) from the harness home directory structure
- `workspace-visibility`: Workspace listing with staleness detection across all onboarded repos
- `cross-repo-openspec`: Cross-repo OpenSpec dashboard — roadmap content and change status read from onboarded repos

### Modified Capabilities
None

## Impact

- New module `src/action_harness/dashboard.py` — data layer functions returning Pydantic models
- New models in `src/action_harness/models.py` — `RepoSummary`, `RepoDetail`, `WorkspaceInfo`, `ChangeInfo`, `RepoRoadmap`
- `src/action_harness/cli.py` — new `repos`, `workspaces`, `roadmap` command groups/commands
- Read-only filesystem access to `~/harness/repos/` and `~/harness/workspaces/`
- Optional `gh` CLI calls for workspace PR status (best-effort, degrades gracefully without `gh`)
