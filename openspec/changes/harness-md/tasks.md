## 1. HARNESS.md Discovery and Reading

- [ ] 1.1 Add a `read_harness_md(worktree_path: Path) -> str | None` function in `worker.py` that reads `HARNESS.md` from the worktree root, returning its contents or None if absent. Empty or whitespace-only files return None.
- [ ] 1.2 Add tests for `read_harness_md`: file exists with content (returns contents), file missing (returns None), file empty (returns None), file with only whitespace (returns None), file with special characters like `{curly braces}` and unicode (returns contents verbatim)

## 2. System Prompt Injection

- [ ] 2.1 Modify `build_system_prompt()` to accept an optional `harness_md: str | None = None` parameter (default None so existing callers are unaffected). When present, append `\n\n## Repo-Specific Instructions\n\n{harness_md}` after the existing role instructions
- [ ] 2.2 Update `dispatch_worker()` to call `read_harness_md()` and pass the result to `build_system_prompt()`
- [ ] 2.3 Add tests for prompt construction: with HARNESS.md content, without HARNESS.md, verify content is appended verbatim

## 3. Documentation

- [ ] 3.1 Add a HARNESS.md section to the project CLAUDE.md explaining the convention: what it is, what belongs in it vs CLAUDE.md vs AGENTS.md, and recommended max length
- [ ] 3.2 Create a `HARNESS.md` in the action-harness repo root with instructions specific to this project (e.g., always run `uv run pytest -v` after changes, use `typer.echo(..., err=True)` for logging, run opsx:apply for OpenSpec changes)

## 4. Validation

- [ ] 4.1 Run full test suite (`uv run pytest -v`) and verify no regressions
- [ ] 4.2 Run lint and type checks (`uv run ruff check .` and `uv run mypy src/`)
