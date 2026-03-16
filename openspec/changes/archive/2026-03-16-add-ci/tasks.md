## 1. Create CI Workflow [no dependencies]

- [x] 1.1 Create `.github/workflows/ci.yml` with: name `CI`, triggers on `pull_request` and `push` to `main`, single job `check` on `ubuntu-latest`, steps: checkout (`actions/checkout@v4`), setup uv (`astral-sh/setup-uv@v4` with `enable-cache: true`), `uv sync`, `uv run pytest -v`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src/`
- [x] 1.2 Verify the workflow YAML is valid (no syntax errors). Check that the `on` triggers and job structure are correct.

## 2. Validation [depends: 1]

- [x] 2.1 Run `uv run pytest -v` locally and verify all tests pass
- [x] 2.2 Run `uv run ruff check .` and `uv run mypy src/` locally and verify clean
- [x] 2.3 Verify `.github/workflows/ci.yml` exists and contains the expected steps
