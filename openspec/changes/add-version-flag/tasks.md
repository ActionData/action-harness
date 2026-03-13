## 1. Implementation

- [ ] 1.1 In `src/action_harness/__init__.py`: add `__version__ = "0.1.0"`
- [ ] 1.2 In `src/action_harness/cli.py`: add a `--version` option to the `@app.callback()` that prints the version and exits. Import `__version__` from `action_harness`.
- [ ] 1.3 In `tests/test_cli.py`: add a test that invokes `action-harness --version` via CliRunner and asserts the output contains "0.1.0" and exit code is 0.

## 2. Validation

```bash
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
```
