## 1. Interactive Dispatch Function

- [x] 1.1 Add `dispatch_lead_interactive()` to `lead.py` — spawns `claude` (without `-p`) with `--system-prompt` for the lead persona and `--append-system-prompt` for gathered context. Passes the user prompt as a positional argument. Uses `subprocess.run` with inherited stdio (no `capture_output`). Returns the exit code. Includes timeout (7200s) and error handling matching `dispatch_lead`.

## 2. CLI Changes

- [x] 2.1 Add `--interactive / --no-interactive` flag to the `lead` command (default: True). When `--dispatch` is provided, automatically set interactive to False. If both `--interactive` and `--dispatch` are explicitly provided, exit with error: "--interactive and --dispatch are mutually exclusive".
- [x] 2.2 Route the `lead` command: when interactive mode is active, call `dispatch_lead_interactive()` and skip plan parsing / display / dispatch logic. When non-interactive, use existing `dispatch_lead()` + `parse_lead_plan()` path.

## 3. Tests

- [ ] 3.1 Add unit tests for `dispatch_lead_interactive()` — verify the subprocess command is constructed correctly (no `-p`, `--system-prompt`, `--append-system-prompt`, positional prompt). Mock `subprocess.run`.
- [ ] 3.2 Add CLI tests for the interactive flag — verify `--dispatch` implies non-interactive, verify `--interactive --dispatch` errors, verify default is interactive mode.

## 4. Validation

- [ ] 4.1 Run full validation suite: `uv run pytest -v`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src/`. Fix all failures.
