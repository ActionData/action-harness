## Context

The lead agent currently runs as a foreground `subprocess.run()` call inside the terminal that invoked `harness lead start`. When that terminal closes — SSH disconnect, tab close, laptop lid — the subprocess (and the Claude Code session) dies immediately. There's no way to reconnect.

The existing lead infrastructure already has:
- **Lead registry** (`lead_registry.py`): state persistence via YAML, PID-based locking, session IDs, clone provisioning.
- **Lead dispatch** (`lead.py`): `dispatch_lead_interactive()` spawns `claude` with inherited stdio.
- **CLI subcommands** (`cli.py`): `start`, `list`, `retire` under `harness lead`.

Gas Town's Mayor pattern provides the reference architecture: wrap the agent process in a tmux session for persistence and multi-terminal attach.

## Goals / Non-Goals

**Goals:**
- Lead sessions survive terminal disconnects, SSH drops, and tab closes
- Any terminal can attach to a running lead session (`harness lead attach`)
- Clean lifecycle: start, stop, attach, reset, status
- Existing lock system integrates with tmux (tmux server PID or pane PID for liveness)
- Backward-compatible: `--no-detach` preserves current foreground behavior

**Non-Goals:**
- IDE/ACP headless mode (Gas Town has this; we don't need it yet)
- Multiple simultaneous viewers of the same session (tmux supports this natively, but we won't build UI around it)
- Remote attach across machines (tmux is local-only; SSH provides the bridge)
- Replacing Claude Code's own session resume — we use tmux for terminal persistence, Claude Code `--resume` for conversation continuity

## Decisions

### 1. tmux as the persistence layer

**Choice**: Wrap `claude` CLI invocation in a detached tmux session.

**Alternatives considered**:
- **screen**: Less ubiquitous on modern systems, weaker scripting API.
- **Custom daemon + Unix socket**: Much more code, reinvents what tmux already does. Would need our own attach protocol.
- **nohup + tail -f**: No real attach/detach — can only view output, not interact.

**Rationale**: tmux is installed on virtually every Linux/macOS dev machine, has a clean scripting API (`tmux new-session -d`, `tmux attach-session`, `tmux send-keys`), and handles all the terminal multiplexing we need. Zero custom daemon code.

### 2. Session naming: `harness-lead-{repo_name}-{lead_name}`

**Rationale**: Must be unique across repos (multiple repos can have leads) and across lead names within a repo. The repo_name comes from the existing `derive_repo_name()` function. tmux session names allow alphanumeric, dash, underscore — we'll sanitize accordingly.

### 3. Graceful stop via `tmux send-keys`

**Choice**: `harness lead stop` sends `/exit` to the Claude Code session via `tmux send-keys`, waits briefly, then kills the tmux session if still alive.

**Alternatives considered**:
- **SIGTERM to claude PID**: Works but skips Claude Code's own cleanup (conversation save, etc).
- **Kill tmux session immediately**: Loses any pending output. No graceful shutdown.

**Rationale**: Sending `/exit` lets Claude Code shut down cleanly. The fallback kill ensures we never leave zombie sessions.

### 4. `start` becomes tmux-backed by default

**Choice**: `harness lead start` creates a detached tmux session and then auto-attaches. Current foreground behavior moves behind `--no-detach`.

**Rationale**: The whole point of this change is persistence by default. Users who want foreground mode (CI, scripts) opt in explicitly. The auto-attach after start means the UX feels identical to today — you still land in an interactive session — but now you can detach and reattach.

### 5. Lock system integration

**Choice**: Store the tmux session name in the lock file alongside the PID. `is_lead_active()` checks both PID liveness (existing) and tmux session existence (`tmux has-session`).

**Rationale**: Belt and suspenders. PID check catches process death. tmux check catches cases where the process is alive but the tmux session was manually killed. Either failure means the lead is not truly active.

### 6. New module: `tmux.py`

**Choice**: All tmux interaction goes in a dedicated `src/action_harness/tmux.py` module.

**Rationale**: Keeps tmux subprocess calls isolated. Easy to test (mock subprocess). lead.py and cli.py import tmux functions rather than embedding tmux commands inline. Functions: `create_session()`, `attach_session()`, `kill_session()`, `has_session()`, `send_keys()`, `session_pane_pid()`, `is_tmux_available()`.

## Risks / Trade-offs

- **[tmux not installed]** → Validate at command entry with `is_tmux_available()`. Clear error message: "tmux is required for persistent lead sessions. Install tmux or use --no-detach for foreground mode." Falls back gracefully.
- **[tmux inside tmux]** → Attaching from inside an existing tmux session works but requires `TMUX` env var handling. We'll detect this and warn but not block (tmux handles nested sessions via prefix key).
- **[Session name collisions]** → Sanitize repo_name to remove characters tmux doesn't allow. Use the existing `slugify` module.
- **[Stale tmux sessions]** → `harness lead status` detects and reports orphaned sessions. `harness lead reset` cleans them up. The existing stale-lock cleanup in `acquire_lock()` extends to tmux sessions.
- **[Claude Code session resume after reattach]** → tmux preserves the terminal session, so the Claude Code process is still running with full context. No resume needed unless the process actually died. If it died, `attach` detects this and offers to restart.

## Open Questions

- Should `harness lead attach` with no running session prompt before starting, or just auto-start silently? (Leaning: auto-start with a log message, matching Gas Town behavior.)
- Should `harness lead` (bare, no subcommand) continue to forward to `start`, or should it forward to `attach` (start if needed)? The latter is more ergonomic for the SSH-attach use case. (Leaning: change to attach-or-start.)
