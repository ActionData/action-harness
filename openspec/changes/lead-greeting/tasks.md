## 1. Structured Context Model

- [ ] 1.1 In `lead.py`: add a `LeadContext` dataclass (using `@dataclass`) with fields: `full_text: str` (the existing flat context string), `repo_name: str`, `active_changes: list[str]` (names of active changes), `completed_changes: list[str]` (recently completed), `ready_changes: list[str]` (ready for implementation), `recent_run_stats: tuple[int, int] | None` (pass_count, total_count — None if no runs), `has_roadmap: bool`, `has_claude_md: bool`. Import from `dataclasses`.
- [ ] 1.2 In `lead.py`: modify `gather_lead_context` to return `LeadContext` instead of `str`. Populate the new fields from the gathered sections. Extract `repo_name` from `repo_path.name`. Parse ready changes from `_gather_ready_changes`. Parse recent run stats from `_gather_recent_runs`. Set `has_roadmap` and `has_claude_md` based on whether those sections were found. The `full_text` field contains the same assembled string as before.
- [ ] 1.3 In `cli.py`: update all call sites of `gather_lead_context` — use `lead_context.full_text` where the flat string was previously used (in both interactive and non-interactive dispatch calls).

## 2. Greeting Builder

- [ ] 2.1 In `lead.py`: add `build_greeting(ctx: LeadContext) -> str` function. Build a concise prompt message that includes: (a) "You are leading {repo_name}." (b) If active changes exist: "Active changes: {comma-separated names}." (c) If ready changes exist: "Ready to implement: {comma-separated names}." (d) If recent run stats: "Recent runs: {pass}/{total} passed." (e) Final line: "Greet me with a brief status summary and suggest 2-3 directions we could go." Log the built greeting to stderr.

## 3. Wire Greeting into Interactive Dispatch

- [ ] 3.1 In `lead.py:dispatch_lead_interactive`: change the `context` parameter from `str` to `LeadContext`. Use `context.full_text` for the `--append-system-prompt` value. When `prompt` is `None`, call `build_greeting(context)` and use the result as the positional argument instead of omitting it.
- [ ] 3.2 In `cli.py`: pass the `LeadContext` object (not `.full_text`) to `dispatch_lead_interactive`. For `dispatch_lead` (non-interactive), pass `lead_context.full_text` since it still expects a string.

## 4. Tests

- [ ] 4.1 In `tests/test_lead.py`: test `build_greeting` — returns string containing repo name, active changes, ready changes, and run stats when all fields populated. Returns minimal greeting when fields are empty/None.
- [ ] 4.2 In `tests/test_lead.py`: test `gather_lead_context` returns `LeadContext` with `full_text` populated and `repo_name` set to the directory name.
- [ ] 4.3 In `tests/test_lead.py`: update `test_none_prompt_omits_positional_arg` — it should now verify that when prompt is None, the built greeting IS passed as a positional argument (behavior change). Rename to `test_none_prompt_uses_built_greeting`.
- [ ] 4.4 In `tests/test_lead.py`: update any other tests broken by the `context` parameter type change from `str` to `LeadContext` in `dispatch_lead_interactive`.

## 5. Validation

```bash
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
```
