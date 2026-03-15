## 1. Implementation

- [x] 1.1 In `evaluator.py`: add `import os` to the imports section. Before the `for` loop in `run_eval` (after line 44), create `clean_env = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "VIRTUAL_ENV_PROMPT")}`. Pass `env=clean_env` to the single `subprocess.run` call on line 54.

## 2. Tests

- [x] 2.1 In `tests/test_evaluator.py`: patch `os.environ` as a dict containing `{"VIRTUAL_ENV": "/fake/path", "VIRTUAL_ENV_PROMPT": "fake", "PATH": "/usr/bin", "HOME": "/home/user"}`. Call `run_eval` with mocked `subprocess.run`. Assert every `subprocess.run` call received an `env` kwarg that does NOT contain `VIRTUAL_ENV` or `VIRTUAL_ENV_PROMPT` but DOES contain `PATH` and `HOME`.

## 3. Validation

```bash
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
```
