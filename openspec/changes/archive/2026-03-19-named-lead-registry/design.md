## Context

Today, every `harness lead` invocation is ephemeral. The `dispatch_lead_interactive` function in `src/action_harness/lead.py` spawns a `claude` process with `--name` for display purposes but no `--session-id` or `--resume`. If the session is killed and restarted, all context is lost. There is no mechanism to run multiple purpose-specific leads (e.g., one for UI work, one for infrastructure) or to prevent two leads from running simultaneously against the same repo.

The current CLI is a single `lead` command defined at `cli.py:1541` as a top-level Typer command. It accepts `--repo`, `--interactive/--no-interactive`, `--dispatch`, `--permission-mode`, `--harness-home`, and a positional `prompt` argument.

Repo identity is derived from `repo_path.name` (the directory basename) throughout `lead.py` (lines 367, 536, 618). The harness home is resolved via `_resolve_harness_home` in `cli.py:112` (CLI flag > `HARNESS_HOME` env > `~/harness/`).

The project has an existing pattern for persistent state under `$HARNESS_HOME/projects/<name>/` (see `repo.py:ensure_project_dir`), but leads are intentionally a separate top-level concept because they exist even for unmanaged local repos.

## Goals / Non-Goals

**Goals:**
- Named lead identities with persistent state directories under `$HARNESS_HOME/leads/<repo-name>/<lead-name>/`
- Session continuity via Claude Code `--session-id` on first start and `--resume` on subsequent starts
- Full git clone provisioning for named (non-default) leads, enabling independent branch/rebase operations
- Single-instance locking per lead via PID lockfile with stale detection
- CLI restructuring: `lead` becomes a Typer sub-app with `start`, `list`, `retire` subcommands
- Backward compatibility: `harness lead --repo .` continues to work as an alias for `harness lead start --repo .`
- Default lead (no `--name`) runs against `--repo` path directly (no clone), preserving current behavior

**Non-Goals:**
- Lead memory / conversation persistence (phase 2: `lead-memory`)
- Inter-lead messaging (phase 3: `lead-inbox`)
- Webhook routing to leads (phase 4: `lead-webhook-routing`)
- Lead templates or pre-configured archetypes
- Auto-starting leads on repo events

## Decisions

### D1: Storage layout under `$HARNESS_HOME/leads/`

Leads live at `$HARNESS_HOME/leads/<repo-name>/<lead-name>/` with these files:

```
$HARNESS_HOME/leads/<repo-name>/
  <lead-name>/
    lead.yaml       # LeadState persisted as YAML
    lock            # PID lockfile (contains PID + session_id)
```

**Rationale:** Leads are a top-level concept separate from `projects/` because they work with unmanaged local repos (plain `--repo .`). A lead for a local repo needs a state directory even without a `projects/<name>/` entry. Putting leads under `projects/` would force project registration as a prerequisite.

**Alternative considered:** Store under `projects/<name>/leads/`. Rejected because it couples leads to managed repos, and most users start with local repos.

### D2: LeadState model — Pydantic BaseModel persisted as YAML

```python
class LeadState(BaseModel):
    name: str
    repo_name: str
    purpose: str
    created_at: str          # ISO 8601
    last_active: str         # ISO 8601, updated on each start
    session_id: str          # UUID controlled by harness
    clone_path: str | None   # Absolute path to full git clone (None for default lead)
    repo_path: str           # Absolute path to the repo this lead targets
```

Persisted as YAML via `yaml.dump(state.model_dump())` and loaded via `LeadState.model_validate(yaml.safe_load(...))`. This matches the project's existing pattern for `config.yaml` in `repo.py`.

**Rationale:** Pydantic BaseModel matches the existing model patterns in `models.py` (e.g., `RepoProfile`, `RunManifest`). YAML over JSON for human editability — consistent with `config.yaml` in project dirs.

**Alternative considered:** Dataclass. Rejected because every other persistent model in the codebase is Pydantic.

### D3: Repo-name derivation

The repo-name used as the directory key under `$HARNESS_HOME/leads/` is derived by:

1. If the repo path is a managed repo (under `$HARNESS_HOME/projects/<name>/repo/`), use `<name>` (the project directory name).
2. Otherwise, run `git -C <repo_path> remote get-url origin` and extract the repo name from the URL (strip `.git` suffix, take the last path component).
3. If git remote fails (no remote, not a git repo), fall back to `repo_path.name` (the directory basename).

This logic is extracted into a `derive_repo_name(repo_path: Path, harness_home: Path) -> str` function in `lead_registry.py` so it can be reused.

**Rationale:** Git remote gives a stable name even if the user accesses the repo from different paths. The managed-repo check handles the case where the repo is already cloned under projects/. Directory basename is the last-resort fallback for repos without remotes.

### D4: Clone provisioning — full `git clone`

Named leads (non-default) get a full git clone at `$HARNESS_HOME/leads/<repo-name>/<lead-name>/clone/`. The clone is created via:

```
git clone <source-repo-path-or-remote-url> <clone-dir>
```

The source is the `--repo` path (or the remote URL extracted from it). A full clone (not a worktree) is used because interactive leads may rebase, force-push, switch branches, or run destructive git operations that would conflict with the main checkout or other worktrees sharing the same `.git` directory.

The clone is created lazily on first `lead start` for a named lead. The `clone_path` field in `lead.yaml` records the absolute path.

**Rationale:** Gastown uses full clones for the same reason — independent git state. Worktrees share `.git` and `refs/`, so a rebase in one worktree affects others. For autonomous pipeline workers this is fine (short-lived, single-branch), but interactive leads are long-lived and may do anything.

**Alternative considered:** Worktree. Rejected per proposal rationale — interactive leads need full git independence.

### D5: Session ID management

On first start of a lead, the harness generates a UUID and passes it to `claude --session-id <uuid>`. This UUID is stored in `lead.yaml` as `session_id`.

On subsequent starts, the harness passes `claude --resume <session_id>`. If `--resume` fails (Claude Code returns non-zero because the session is expired/corrupt), the harness:
1. Generates a new UUID
2. Updates `session_id` in `lead.yaml`
3. Falls back to `claude --session-id <new-uuid>`
4. Logs the fallback to stderr

The `--session-id` flag on `claude` lets us control the session ID (rather than Claude generating one), which is essential for resume.

**Rationale:** Claude Code's `--resume` requires the exact session ID. By controlling generation, we can persist and replay it. The fallback ensures a bad session never blocks the user.

### D6: Locking mechanism — PID lockfile

Each lead has a `lock` file containing:
```
<pid>\n<session_id>\n
```

Lock acquisition:
1. Try to read the lock file
2. If it exists, extract PID and check if the process is alive via `os.kill(pid, 0)`
3. If the process is alive, refuse to start (error: "Lead <name> is already running (PID <pid>)")
4. If the process is dead, reclaim the lock (log warning about stale lock)
5. Write the new PID and session_id

Lock release: Delete the lock file. This happens:
- On normal exit (via `try/finally` around the `subprocess.run` call in `dispatch_lead_interactive`)
- Stale locks are auto-reclaimed on next start (step 4 above)

**Rationale:** PID lockfiles are the simplest cross-platform locking mechanism. `os.kill(pid, 0)` doesn't actually send a signal — it checks process existence. Combined with stale detection, this prevents orphaned locks from blocking startup.

**Alternative considered:** `fcntl.flock` / file locking. Rejected because it's platform-specific and doesn't survive process crashes (the lock is released when the file descriptor closes, but the lock file remains and confuses detection).

### D7: CLI restructuring — Typer sub-app

The `lead` command becomes a Typer sub-app with three subcommands:

- `harness lead start` — start or resume a lead (absorbs current `lead` behavior)
- `harness lead list` — list all leads for a repo with status
- `harness lead retire` — remove a lead (delete clone, archive state)

**Backward compatibility:** The current `harness lead --repo .` invocation (no subcommand) must continue to work.

Implementation approach: Define `lead_app = typer.Typer()` and register it on the main app via `app.add_typer(lead_app, name="lead")`. The `start` logic is a registered `@lead_app.command(name="start")`. A separate `@lead_app.callback(invoke_without_command=True)` checks `ctx.invoked_subcommand` — when `None`, it forwards to `start`. The current positional `prompt` argument is converted to `--initial-prompt` option to avoid Typer sub-app parsing conflicts (Typer may interpret subcommand names as positional argument values).

**Rationale:** A callback-only approach with a positional argument would cause Typer to misparse `harness lead start` (interpreting "start" as the prompt value). Splitting into `@lead_app.command("start")` + `@lead_app.callback(invoke_without_command=True)` avoids this while still preserving bare `harness lead --repo .`.

### D8: Default lead behavior

When `--name` is omitted, the lead name is `"default"`. The default lead:
- Runs against the `--repo` path directly (no clone)
- Gets a state directory at `$HARNESS_HOME/leads/<repo-name>/default/`
- Gets a lockfile (preventing two default leads on the same repo)
- Gets session tracking (resume on next start)
- `clone_path` is `None` in `lead.yaml`

**Rationale:** Preserves current behavior exactly. Users who never use `--name` see no difference except that their sessions now resume and have locking protection.

## Risks / Trade-offs

**[Risk] PID reuse on long-lived systems.** Operating systems can reuse PIDs. If a lead crashes and a completely unrelated process gets the same PID, the stale detection will incorrectly think the lead is still running.
**Mitigation:** The lock file stores both PID and session_id. In practice, PID reuse is rare on modern systems with 32-bit PID spaces. If it becomes an issue, we can add a timestamp check (if lock is older than N hours, reclaim regardless).

**[Risk] Clone disk usage.** Full git clones duplicate the entire repo history.
**Mitigation:** `git clone --no-tags --single-branch` to reduce initial size. Users can `retire` leads they no longer need. Future: shallow clones for large repos.

**[Risk] Typer sub-app backward compatibility.** Sub-app routing with positional arguments causes Typer misparse.
**Mitigation:** Convert positional `prompt` to `--initial-prompt` option. Test the exact invocations `harness lead --repo .`, `harness lead --repo . --initial-prompt "prompt"`, and `harness lead start --repo . --name foo` to verify all parse correctly.

**[Risk] Orphaned claude process on `kill -9`.** If the harness process is `kill -9`'d, the `finally` block doesn't run, leaving a stale lock AND an orphaned `claude` process still running on the clone. On next start, stale detection reclaims the lock (harness PID is dead), but the orphaned claude may still be running.
**Mitigation:** This is rare in practice (`kill -9` is exceptional). The orphaned claude process will eventually exit on its own. If this becomes a real problem, the lock file could store both the harness PID and the claude subprocess PID, checking both on stale detection.

**[Risk] Session resume fails silently.** Claude Code may change `--resume` behavior across versions.
**Mitigation:** Always check exit code. On non-zero from `--resume`, fall back to `--session-id` with a new UUID. Log the fallback clearly.

## Open Questions

None. All design decisions are resolved based on the proposal and Gastown comparison.
