# HARNESS.md — action-harness

Instructions for autonomous harness workers operating on this repository.

## Validation

After any code changes, run the full validation suite:

```bash
uv run pytest -v                  # all tests must pass
uv run ruff check .               # no lint violations
uv run ruff format --check .      # formatting must be clean
uv run mypy src/                  # no type errors
```

Fix all failures before committing. Do not skip or ignore test failures.

## Logging

Use `typer.echo(..., err=True)` for all diagnostic output. Never use `print()` or write to stdout for logging — stdout is reserved for final output.

## OpenSpec changes

When implementing an OpenSpec change, use the `opsx-apply` skill to work through the task list. Commit incrementally after completing each task or logical group of tasks.

## Code conventions

- No `Any` types — use specific types or unions
- No silent failures — log errors that affect task flow
- Functions that perform I/O must log at entry (inputs) and exit (outcome) to stderr
- Every `subprocess.run()` must include `timeout=` (120s for CLI tools, 600s for long ops). Catch `subprocess.TimeoutExpired` alongside `FileNotFoundError`/`OSError`.
- Never use bare `assert` for type narrowing — use explicit `if x is None: raise ValueError(...)` instead
- Never use `# type: ignore` — fix the type mismatch instead. Thread the correct Literal/union type through the call chain.
- Use `\b` word boundaries in regex when matching keywords that could be substrings
- Include actual error text in error messages, not generic descriptions
- Validate prerequisites (CLI availability, file existence) before operations that depend on them
- When adding I/O functions, match the error handling pattern of existing functions in the same module
- Search for existing implementations before writing utility functions — import, don't copy
