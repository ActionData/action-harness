## Why

The lead agent dies when you close a terminal or disconnect SSH. There's no way to reconnect to a running lead from another shell session. This is the single biggest friction point for remote work: start a lead on the machine, SSH in later, and you've lost the conversation. Gas Town solved this with tmux-backed persistence (`gt mayor start/stop/attach`), and the pattern maps directly to action-harness.

## What Changes

- **tmux-backed lead sessions**: `harness lead start` launches Claude Code inside a detached tmux session instead of a foreground subprocess. The session survives terminal disconnects, SSH drops, and tab closes.
- **Attach from any terminal**: `harness lead attach` connects to a running lead's tmux session. Smart behavior: auto-starts if not running, restarts runtime if tmux pane exists but process exited.
- **Lifecycle commands**: `harness lead stop` for graceful shutdown (sends exit to Claude Code, then kills tmux session). `harness lead reset` for stop + fresh start with a new session ID.
- **Status enhancement**: `harness lead status` (replaces or augments `list`) shows whether each lead is running, its tmux session name, PID, and uptime.
- **Session naming convention**: tmux sessions named `harness-lead-{repo_name}-{lead_name}` for uniqueness across repos.
- **Backward compatibility**: Direct foreground mode preserved via `--no-detach` flag for CI, scripting, or users who prefer the current behavior.

## Capabilities

### New Capabilities

- `tmux-session-management`: tmux session lifecycle (create detached, attach, kill, status check) for lead agents. Covers session naming, process health detection, and graceful shutdown.
- `lead-lifecycle-commands`: CLI subcommands `stop`, `attach`, `reset`, and enhanced `status`. Integrates with existing lock system and lead registry.

### Modified Capabilities

_(none — existing lead-interactive and named-lead-registry specs are implementation details that don't need requirement-level changes; the new capabilities layer on top)_

## Impact

- **Code**: `src/action_harness/cli.py` (lead subcommands), `src/action_harness/lead.py` (dispatch functions), `src/action_harness/lead_registry.py` (state model gets tmux fields)
- **Dependencies**: Requires `tmux` on the host. Must validate availability at startup and provide a clear error.
- **State model**: `LeadState` gains optional `tmux_session` field for tracking the tmux session name.
- **Lock system**: Existing PID-based locking integrates naturally — tmux session PID replaces direct subprocess PID.
- **Breaking**: None. Current `start` behavior preserved behind `--no-detach`.
