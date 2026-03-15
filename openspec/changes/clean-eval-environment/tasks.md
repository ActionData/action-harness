## 1. Implementation

- [ ] 1.1 In `evaluator.py:run_eval`: before the command loop, create a clean env: `clean_env = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "VIRTUAL_ENV_PROMPT")}`. Pass `env=clean_env` to the `subprocess.run` call.

## 2. Tests

- [ ] 2.1 In `tests/test_evaluator.py`: add test that verifies `subprocess.run` is called with an `env` kwarg that does NOT contain `VIRTUAL_ENV`. Mock `os.environ` to include `VIRTUAL_ENV=/fake/path` and verify it's stripped.

## 3. Validation

```bash
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
```
