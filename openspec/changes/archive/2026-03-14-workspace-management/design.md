## Context

Today the harness requires `--repo <local-path>` pointing to an existing git checkout. Worktrees are created in `/tmp/action-harness-*` and lost on reboot. The operator must manually clone repos, manage directories, and clean up. This is fine for self-hosting on one repo but doesn't scale.

The harness should own the full lifecycle: clone → workspace → agent work → PR → cleanup.

## Goals / Non-Goals

**Goals:**
- Accept GitHub `owner/repo` shorthand or full URL as `--repo`
- Clone repos to a persistent, configurable location
- Create workspaces (worktrees) in a structured path the operator can find
- Full repo context available in workspaces (CLAUDE.md, .claude/ skills, MCP servers, etc.)
- `clean` command for workspace lifecycle management

**Non-Goals:**
- Multi-remote support (one origin per repo)
- Workspace sharing between concurrent pipeline runs (each change gets its own workspace)
- Authentication management (assumes `gh auth` and SSH keys are configured)

## Decisions

### 1. Regular clone, not bare clone

Clone repos with a regular `git clone`, not `--bare`. The workspace worktrees need full repo context — CLAUDE.md, .claude/ skills, MCP config, pyproject.toml, etc. A bare clone has no working directory and tools that expect repo structure (like `openspec`, `claude` with CLAUDE.md loading) would not work correctly.

**Why:** The agent needs the same environment a developer would have. A regular clone provides that. The main checkout won't be modified — all work happens in worktrees branched off of it.

### 2. Directory structure under `HARNESS_HOME`

```
$HARNESS_HOME/              # default ~/harness/
├── repos/<repo-name>/      # regular git clones
└── workspaces/<repo-name>/<change-name>/   # worktrees
```

`repo-name` is derived from the URL: `github.com/ActionData/action-harness` → `action-harness`. If there's a collision (two different orgs, same repo name), use `owner-repo` as the directory name.

**Why:** Flat by default (most people work with uniquely named repos), qualified when needed (collision detection).

### 3. `--repo` accepts three forms

- Local path: `--repo .` or `--repo /abs/path` — existing behavior, no cloning
- GitHub shorthand: `--repo owner/repo` — clones to harness home if needed
- Full URL: `--repo https://github.com/owner/repo` or `--repo git@github.com:owner/repo.git` — same

Detection: if the value contains `/` but is not an existing directory path, treat as remote. If it starts with `http`, `git@`, or matches `owner/repo` pattern, clone.

**Why:** Minimal friction. The operator types what's natural — a path for local, a name for remote.

### 4. Fetch before creating workspace

When using a managed repo (cloned to harness home), always `git fetch origin` before creating the workspace worktree. This ensures the workspace branches from the latest remote state.

**Why:** Stale clones produce worktrees based on old code. Fetching is cheap and prevents subtle bugs.

### 5. `HARNESS_HOME` env var with `--harness-home` CLI override

Default: `~/harness/`. Override with `HARNESS_HOME` env var or `--harness-home` CLI flag (CLI takes precedence).

**Why:** Env var for persistent config, CLI flag for one-off overrides. Follows standard Unix conventions.

### 6. `action-harness clean` subcommand

`clean` removes workspaces. Options:
- `action-harness clean --repo owner/repo` — remove all workspaces for a repo
- `action-harness clean --repo owner/repo --change name` — remove a specific workspace
- `action-harness clean --all` — remove all workspaces (keeps cloned repos)

Does NOT remove cloned repos. Those persist until manually deleted.

**Why:** Workspaces are the large, disposable artifacts. Clones are small and expensive to re-download. Separate lifecycle.

## Risks / Trade-offs

**[Risk] Disk space from accumulated clones and workspaces.**
→ Mitigation: `clean` command handles workspaces. Clones are small relative to workspaces. Future: `clean --repos` option to remove clones too.

**[Risk] Repo name collisions across GitHub orgs.**
→ Mitigation: Detect collision, fall back to `owner-repo` directory name. Log the decision.

**[Trade-off] Regular clone duplicates repo data vs bare clone.**
→ Acceptable. The clone is a one-time cost per repo. Agent tools and context require a full working directory. Bare clone would break too many assumptions.
