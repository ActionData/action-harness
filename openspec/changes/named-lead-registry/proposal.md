## Why

Leads are ephemeral today. Every `harness lead` session starts fresh — no memory of prior conversations, no accumulated expertise, no continuity. If you kill a session and start a new one, all context is lost. You also can't run purpose-built leads (one for UI bugs, one for feature specs) because there's no identity system to distinguish them.

This means leads can't build expertise over time, and there's no protection against running two leads on the same repo simultaneously (which would create conflicting dispatches).

Gastown solves this with "crew" — persistent, user-managed workers with their own clones, identity, and lifecycle. We need the same foundation.

## What Changes

- Named lead identities stored in `$HARNESS_HOME/leads/<repo-name>/<lead-name>/`
- Each lead gets its own full git clone for workspace isolation (not a worktree — interactive leads may rebase, switch branches, or run destructive git operations that would conflict with the main checkout or other worktrees sharing the same `.git` directory)
- `harness lead start --name <name> --purpose "..." --repo .` implicitly registers on first use, or resumes if the lead already exists
- Session resume via `claude --session-id <uuid>` on first start (so we control the ID) and `claude --resume <session_id>` on subsequent starts. Fallback to fresh session with a new controlled session ID when resume fails.
- Single-instance locking via PID lockfile + session_id validation. Stale lock detection via `os.kill(pid, 0)` — if the PID is dead, the lock is reclaimed automatically.
- `harness lead list --repo .` shows all leads with status (active/idle/stopped)
- `harness lead retire <name> --repo .` cleans up a lead (removes clone, archives state)
- A "default" lead is used when `--name` is omitted. The default lead runs against the `--repo` path directly (no clone), preserving current behavior. It still gets a state directory and lockfile for session tracking and locking.

### Storage layout

```
$HARNESS_HOME/leads/<repo-name>/
  default/
    lead.yaml
    session_id
    lock
  ui-bugs/
    lead.yaml
    session_id
    lock
    clone_path       # points to the full git clone location
```

This is independent of the `projects/<repo>/` layout. Leads are a top-level concept under `$HARNESS_HOME` because they exist whether or not a repo is "managed" by the harness. Local repos (`--repo .`) work without a project directory.

### CLI structure

The `lead` command becomes a Typer sub-app to support subcommands while keeping backward compatibility:

- `harness lead start --repo . [--name <name>] [--purpose "..."]` — start or resume a lead (replaces current `harness lead`)
- `harness lead list --repo .` — show all leads with status
- `harness lead retire <name> --repo .` — clean up a lead

The current `harness lead --repo .` invocation is preserved as an alias for `harness lead start --repo .`.

## Capabilities

### New Capabilities
- `named-lead-registry`: Lead identity creation, storage, lookup, and lifecycle management
- `lead-locking`: Single-instance enforcement via PID lockfile and session validation
- `lead-workspace`: Full git clone provisioning per named lead

### Modified Capabilities
- `lead-interactive`: Extended to accept `--name` and `--purpose`, resolve lead identity, resume sessions

## Impact

- `src/action_harness/cli.py` — `lead` command becomes Typer sub-app with `start`, `list`, `retire` subcommands
- `src/action_harness/lead.py` — session resume logic, clone management, lock acquisition/release
- New module `src/action_harness/lead_registry.py` — lead identity CRUD, state persistence, lock management
- `lead.yaml` schema: `name`, `purpose`, `created_at`, `last_active`, `session_id`, `clone_path`

## Prerequisites

None. This is the foundation for lead-memory, lead-inbox, and lead-webhook-routing.

## Inspiration

Gastown's "crew" concept: persistent, user-managed workers with full git clones, named tmux sessions, and explicit lifecycle (add/start/attach/remove). We adapt this to Claude Code's session model (`--resume`, `--session-id`, `--name`) and the harness's file-based state conventions.
