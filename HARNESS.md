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

When implementing an OpenSpec change, use the `opsx:apply` skill to work through the task list. Commit incrementally after completing each task or logical group of tasks.

## Code conventions

- No `Any` types — use specific types or unions
- No silent failures — log errors that affect task flow
- Functions that perform I/O must log at entry (inputs) and exit (outcome) to stderr
