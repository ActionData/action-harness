## Context

The harness home directory (`~/harness/` or `$HARNESS_HOME`) has a known structure: `repos/<name>/` for cloned repos, `workspaces/<name>/<change>/` for worktrees. Repo-level config lives in the target repos themselves (HARNESS.md, `.harness/protected-paths.yml`, `openspec/`). All the data for a dashboard already exists on disk — it just needs structured reading.

Today the only commands are `run` and `clean`. There's no "show me what I have" capability.

## Goals / Non-Goals

**Goals:**
- Read-only visibility into onboarded repos, workspaces, and cross-repo OpenSpec state
- Presentation-agnostic data layer (Pydantic models) that CLI, TUI, or web can consume
- Graceful degradation — missing files, missing `gh` CLI, repos without OpenSpec all handled without errors

**Non-Goals:**
- Mutating config (editing HARNESS.md, changing settings) — that's a future concern
- Run management (starting/stopping/monitoring pipeline runs)
- TUI or web frontend — this change builds the data layer and CLI only
- Real-time updates or watching — these are point-in-time reads

## Decisions

### 1. Single module for the data layer

All read functions live in `dashboard.py`. Each function takes `harness_home: Path` and returns a Pydantic model. No classes, no state — pure functions over filesystem.

**Rationale:** Matches the project's "minimal abstraction" principle. The module is a bag of functions that read directories and parse files. A future TUI or web layer imports these functions directly.

### 2. Direct file reads for OpenSpec data, not CLI subprocess

Read `tasks.md` checkboxes, `ROADMAP.md` content, and change directory structure directly rather than shelling out to `openspec` CLI.

**Rationale:** Faster, no dependency on `openspec` being installed in target repos, and the formats are simple (markdown checkboxes, directory existence). The parsing is trivial — count `- [x]` vs `- [ ]` lines.

**Alternative considered:** `openspec status --json` per repo. Rejected because it adds subprocess overhead per repo, requires openspec CLI in each repo's environment, and we only need basic counts.

### 3. Staleness detection: time-based with optional PR check

A workspace is stale when: the last commit on its branch is older than 7 days AND there is no open PR for the branch. The PR check uses `gh pr list --head <branch> --json number --limit 1` and is best-effort — if `gh` fails, the workspace is marked stale based on time alone.

**Rationale:** Simple, covers the common case (abandoned worktrees from failed runs). The PR check prevents falsely marking long-running reviewed PRs as stale.

### 4. CLI command structure

```
harness repos                      # list all repos
harness repos show <name>          # detail view of one repo
harness workspaces                 # all workspaces across repos
harness roadmap                    # cross-repo OpenSpec view
```

`repos` is a typer sub-app with `invoke_without_command=True` on its callback. When invoked without a subcommand, the callback runs the listing logic. `show` is a command on the sub-app.

```python
repos_app = typer.Typer(name="repos")
app.add_typer(repos_app)

@repos_app.callback(invoke_without_command=True)
def repos_list(ctx: typer.Context, json_output: bool = False):
    if ctx.invoked_subcommand is not None:
        return
    # list repos logic here

@repos_app.command()
def show(name: str, json_output: bool = False):
    # detail view logic here
```

`workspaces` and `roadmap` are top-level commands on the main `app`.

**Rationale:** Groups repo-specific commands under `repos`, keeps cross-cutting views (`workspaces`, `roadmap`) at the top level for quick access. The `invoke_without_command` pattern is the standard typer approach for sub-apps that also act as commands.

### 5. Repo discovery by scanning `repos/` directory

A repo is "onboarded" if it has a directory under `~/harness/repos/`. No registration, no config file listing repos. The filesystem is the source of truth.

**Rationale:** Matches the existing workspace-management design. `harness run --repo owner/repo` clones into `repos/`, so discovery is just `ls repos/`.

### 6. Output formatting

CLI output uses the same style as `openspec view` — unicode box characters, aligned columns, status indicators (✓, ✗, ◉). No color codes (keeps it simple and pipe-friendly). `--json` flag on each command for machine-readable output.

### 7. Example output

`harness repos`:
```
Onboarded Repos
════════════════════════════════════════════════════════════
  analytics-monorepo    HARNESS.md: ✓  Protected: ✗  Workspaces: 2  Changes: 3 active, 5 completed
  action-harness        HARNESS.md: ✓  Protected: ✓  Workspaces: 1  Changes: 4 active, 12 completed
════════════════════════════════════════════════════════════
```

`harness workspaces`:
```
Workspaces
════════════════════════════════════════════════════════════
analytics-monorepo
  add-logging        harness/add-logging        2d ago
  fix-auth           harness/fix-auth          10d ago  (stale)

action-harness
  review-tolerance   harness/review-tolerance   1d ago
════════════════════════════════════════════════════════════
```

`harness roadmap`:
```
Cross-Repo Roadmap
════════════════════════════════════════════════════════════
action-harness (4 active, 12 completed)
  ◉ review-tolerance   [██████████░░░░░░░░░░] 50%
  ◉ baseline-eval      [░░░░░░░░░░░░░░░░░░░░] 0%
  ◉ rollback-tags      [░░░░░░░░░░░░░░░░░░░░] 0%
  ◉ test-cleanup       [░░░░░░░░░░░░░░░░░░░░] 0%

analytics-monorepo (3 active, 5 completed)
  ◉ add-logging        [████████░░░░░░░░░░░░] 40%
  ◉ fix-auth           [░░░░░░░░░░░░░░░░░░░░] 0%
  ◉ data-export        [░░░░░░░░░░░░░░░░░░░░] 0%
════════════════════════════════════════════════════════════
```

## Risks / Trade-offs

**[Parsing OpenSpec files directly is fragile]** → If the checkbox format in `tasks.md` changes, the parser breaks. Mitigation: the format is a well-established convention (`- [x]` / `- [ ]`), and the parser is a few lines of regex. If it breaks, it returns 0/0 counts rather than erroring.

**[Workspace staleness heuristic may be wrong]** → 7 days is arbitrary. A long-running implementation might have no commits for a week while waiting for review. Mitigation: the PR check helps, and the staleness indicator is informational — `harness clean` is a separate deliberate action.

**[Cross-repo OpenSpec reads may be slow with many repos]** → Each repo requires reading several files. Mitigation: these are local filesystem reads (sub-millisecond per file). Even 50 repos would be instant. If it becomes an issue, add parallelism later.
