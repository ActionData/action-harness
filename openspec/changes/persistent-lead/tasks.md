## 1. tmux module

- [ ] 1.1 Create `src/action_harness/tmux.py` with `is_tmux_available()` function that checks for tmux on PATH via `shutil.which("tmux")`. Returns bool.
- [ ] 1.2 Implement `create_session(session_name: str, command: list[str], cwd: Path) -> None` — runs `tmux new-session -d -s {session_name} {command}`. Raises RuntimeError if session already exists or tmux fails. Includes timeout=120.
- [ ] 1.3 Implement `attach_session(session_name: str) -> int` — runs `tmux attach-session -t {session_name}` with inherited stdio. Returns exit code. Raises RuntimeError if session doesn't exist.
- [ ] 1.4 Implement `kill_session(session_name: str) -> None` — runs `tmux kill-session -t {session_name}`. Idempotent: no error if session doesn't exist.
- [ ] 1.5 Implement `has_session(session_name: str) -> bool` — runs `tmux has-session -t {session_name}`. Returns True if exit code 0, False otherwise.
- [ ] 1.6 Implement `send_keys(session_name: str, keys: str) -> None` — runs `tmux send-keys -t {session_name} {keys} Enter`. Raises RuntimeError if session doesn't exist.
- [ ] 1.7 Implement `session_pane_pid(session_name: str) -> int | None` — runs `tmux display-message -p -t {session_name} '#{pane_pid}'`. Returns int PID or None if session doesn't exist.
- [ ] 1.8 Implement `sanitize_session_name(name: str) -> str` — replaces characters not allowed in tmux session names (dots, slashes, colons) with dashes.
- [ ] 1.9 Add unit tests for all tmux module functions in `tests/test_tmux.py`. Mock subprocess.run calls. Test error paths (tmux not found, session exists, session not found).

## 2. Lead state model updates

- [ ] 2.1 Add `tmux_session: str | None = None` field to `LeadState` in `lead_registry.py`. Ensure backward compatibility with existing lead.yaml files that lack this field.
- [ ] 2.2 Add helper function `lead_tmux_session_name(repo_name: str, lead_name: str) -> str` that returns `harness-lead-{sanitized_repo}-{sanitized_lead}` using `sanitize_session_name`.
- [ ] 2.3 Update `is_lead_active()` to also check `has_session()` when a tmux_session is stored in state. Lead is active if EITHER PID is alive OR tmux session exists.
- [ ] 2.4 Add tests for the updated state model and session name generation.

## 3. Lead dispatch updates

- [ ] 3.1 Create `dispatch_lead_tmux(repo_path: Path, context: LeadContext, harness_agents_dir: Path, session_name: str, permission_mode: str, session_id: str | None, resume: bool) -> None` in `lead.py`. Builds the same `claude` command as `dispatch_lead_interactive` but passes it to `tmux.create_session()` instead of `subprocess.run()`.
- [ ] 3.2 Add tests for `dispatch_lead_tmux` verifying the correct command is constructed and passed to tmux.

## 4. CLI lifecycle commands

- [ ] 4.1 Add `--no-detach` boolean flag to `lead_start()`. When set, use existing foreground dispatch. When unset (default), use tmux dispatch + auto-attach.
- [ ] 4.2 Update `lead_start()` to: validate tmux available (unless --no-detach), create detached tmux session, store tmux_session in LeadState, then attach. If session already running, attach instead of creating.
- [ ] 4.3 Implement `harness lead stop` subcommand: resolve lead state, send `/exit` via send_keys, wait up to 10s polling has_session every 1s, kill_session if still alive, release lock.
- [ ] 4.4 Implement `harness lead attach` subcommand: check if session running, if yes attach, if tmux session exists but process died then kill and restart, if no session then auto-start (call start logic).
- [ ] 4.5 Implement `harness lead reset` subcommand: call stop logic, generate new session_id in LeadState, save state, call start logic.
- [ ] 4.6 Implement `harness lead status` subcommand: list leads for repo, for each check if tmux session active, display name/status/tmux_session/pane_pid/last_active.
- [ ] 4.7 Change bare `harness lead` (callback with invoke_without_command) to forward to attach logic instead of start, so SSH-attach is the default ergonomic path.
- [ ] 4.8 Add integration tests for lifecycle commands: test start creates tmux session name in state, stop clears it, attach auto-starts, reset generates new session_id. Mock tmux module calls.

## 5. Validation and polish

- [ ] 5.1 Validate tmux availability at the top of every tmux-dependent command path. Provide clear error message with `--no-detach` suggestion.
- [ ] 5.2 Handle nested tmux detection: if `TMUX` env var is set, log a warning "Already inside a tmux session — nested attach may require prefix key" but proceed.
- [ ] 5.3 Update CLI help text and docstrings for all new and modified subcommands.
- [ ] 5.4 Run full validation suite: pytest, ruff check, ruff format, mypy.
