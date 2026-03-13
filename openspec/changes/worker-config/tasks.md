## 1. CLI Flags

- [ ] 1.1 In `cli.py`: add `--model` option (str | None, default None). Pass to pipeline.
- [ ] 1.2 In `cli.py`: add `--effort` option (str | None, default None). Use typer's `click_type=click.Choice(["low", "medium", "high", "max"])` or equivalent to validate choices. Pass to pipeline.
- [ ] 1.3 In `cli.py`: add `--max-budget-usd` option (float | None, default None). Pass to pipeline.
- [ ] 1.4 In `cli.py`: add `--permission-mode` option (str, default "bypassPermissions"). Pass to pipeline.
- [ ] 1.5 In `cli.py`: update dry-run output to always show all four config lines after the worker line: `model: {model or 'default'}`, `effort: {effort or 'default'}`, `max-budget-usd: {budget or 'none'}`, `permission-mode: {permission_mode}`.

## 2. Worker Dispatch

- [ ] 2.1 In `worker.py`: add `model: str | None = None`, `effort: str | None = None`, `max_budget_usd: float | None = None`, `permission_mode: str = "bypassPermissions"` parameters to `dispatch_worker`. For `model`, `effort`, and `max_budget_usd`: only append the flag to the `cmd` list when the value is not None. For `permission_mode`: always append `--permission-mode <value>` to the `cmd` list (it has a non-None default).
- [ ] 2.2 In `pipeline.py`: add `model: str | None = None`, `effort: str | None = None`, `max_budget_usd: float | None = None`, `permission_mode: str = "bypassPermissions"` to the `run_pipeline` signature. Pass these to `dispatch_worker()`. Also update `cli.py`'s `run_pipeline(...)` call to pass the new values from CLI options.

## 3. Tests

- [ ] 3.1 In `tests/test_worker.py`: write tests for each flag: (a) `--model opus` in cmd when model="opus", (b) `--model` absent when model=None, (c) `--effort high` in cmd when effort="high", (d) `--effort` absent when effort=None, (e) `--max-budget-usd 5.0` in cmd when max_budget_usd=5.0, (f) `--max-budget-usd` absent when max_budget_usd=None, (g) `--permission-mode bypassPermissions` in cmd with default, (h) `--permission-mode plan` in cmd when permission_mode="plan".
- [ ] 3.2 In `tests/test_cli.py`: test `--help` shows `--model`, `--effort`, `--max-budget-usd`, `--permission-mode`. Test dry-run with custom values contains `model: sonnet`, `effort: high`, `max-budget-usd: 2.0`. Test dry-run with defaults contains `model: default`, `permission-mode: bypassPermissions`.

## 4. Validation

```bash
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
```
