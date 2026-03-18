## Context

The harness home (`~/harness/`) currently uses a flat layout with `repos/` and `workspaces/` as sibling directories. Repo clones go to `repos/<name>/`, worktrees to `workspaces/<name>/<change>/`, catalog frequency data to `repos/<name>/knowledge/`, and run manifests to `.action-harness/runs/` inside each worktree. ~15 path references across 5 modules construct these paths.

## Goals / Non-Goals

**Goals:**
- Single self-contained `projects/<name>/` directory per onboarded repo
- All per-repo state (clone, workspaces, runs, knowledge, config) co-located
- Extensibility point for future per-repo settings (review cycle, lead context, agent overrides)
- Run manifests centralized per-repo (not scattered in worktrees)

**Non-Goals:**
- Migration from old layout (fresh start, no backward compatibility)
- Implementing per-repo configuration UI (just create the file, populate later)
- Changing how git cloning, worktree creation, or fetching works (only paths change)
- Bare repo pattern (shared `.repo.git/` with worktrees only — unnecessary for sequential pipeline)

## Decisions

### 1. Directory structure

```
~/harness/projects/<name>/
├── repo/                    git clone of target repo
├── workspaces/              worktrees, one per change
│   └── <change>/
├── runs/                    run manifests (JSON)
│   └── <run-id>.json
├── knowledge/               catalog frequency data
│   └── findings-frequency.json
└── config.yaml              harness-level repo settings
```

**Rationale:** Everything about a repo is in one place. `harness prime`, `harness repos show`, and the repo-lead can read one directory tree. Removing a project is `rm -rf projects/<name>/`.

**Alternative considered:** Keep `repos/` and `workspaces/` but add symlinks or a registry file. Rejected — adds indirection without solving the "state is scattered" problem.

### 2. `config.yaml` — minimal seed, grow later

Created on first repo onboard with:

```yaml
repo_name: analytics-monorepo
remote_url: git@github.com:ActionData/analytics-monorepo.git
```

Future fields (not implemented in this change):
- `review_cycle: [low, med, high]`
- `auto_merge: true`
- `lead_context: "..."`
- `agent_overrides: {bug-hunter: .harness/agents/bug-hunter.md}`

**Rationale:** Establish the file and location now. Future changes add fields. No need to design the full config schema upfront.

### 3. Run manifests move to `projects/<name>/runs/`

Currently manifests are written to `.action-harness/runs/<run-id>.json` inside the worktree. This is fragile — when the worktree is cleaned up, manifests can be lost. Moving them to `projects/<name>/runs/` makes them persistent and queryable by `harness report`.

The pipeline writes the manifest to `projects/<name>/runs/<run-id>.json` at completion. The `harness report` command reads from this directory.

**Rationale:** Run history is per-repo state, not per-worktree state. Centralizing it makes failure reporting and the repo-lead's context generation straightforward.

### 4. Local repos (--repo .) still work

When `--repo .` or `--repo /abs/path` is used (local, not managed), the harness does NOT create a project directory. Worktrees go to `/tmp/` as before. This path is unchanged — project consolidation only affects managed repos (cloned via `owner/repo` or URL).

**Rationale:** Local repos are the operator's own checkout. The harness shouldn't reorganize their filesystem. The project directory is for repos the harness manages.

### 5. Name collision handling stays the same

Currently `orgA/utils` → `repos/utils/`, collision → `repos/orgA-utils/`. Same logic, new path: `projects/utils/repo/`, collision → `projects/orgA-utils/repo/`.

### 6. No migration

Old `repos/` and `workspaces/` directories are not migrated. The operator can delete them manually. The harness will re-clone on next run against a managed repo.

**Rationale:** Only one managed repo exists currently (analytics-monorepo). Re-cloning is trivial. Migration code adds complexity for a one-time operation.

## Risks / Trade-offs

**[Wider refactor than typical]** → ~15 path references across 5 files. Mitigation: the changes are mechanical (path prefix swaps), not logic changes. Tests verify the new paths.

**[Run manifests in a new location]** → `harness report` reads from the new path. Old manifests (in worktree `.action-harness/`) are not migrated. Mitigation: acceptable — historical data loss is minimal and we're starting fresh.

**[`config.yaml` is mostly empty]** → Creates a file with 2 fields that nothing reads yet. Mitigation: establishing the convention is the point. Future changes add fields. The file's existence tells the harness "this is a managed project."
