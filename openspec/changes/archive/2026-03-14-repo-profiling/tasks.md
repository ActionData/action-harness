## 1. RepoProfile Model and Profiler Module

- [x] 1.1 Create `src/action_harness/profiler.py` with a `RepoProfile` Pydantic model containing fields: `ecosystem: str`, `eval_commands: list[str]`, `source: Literal["claude-md", "convention", "fallback"]`, `marker_file: str | None = None`. Import `BOOTSTRAP_EVAL_COMMANDS` from `evaluator.py` for fallback.

- [x] 1.2 Implement `_detect_ecosystem(repo_path: Path) -> tuple[str, str | None]` in `profiler.py`. Scan `repo_path` for marker files in priority order: `pyproject.toml`, `setup.py`, `package.json`, `Cargo.toml`, `go.mod`, `Makefile`, `Gemfile`. Return `(ecosystem_name, marker_filename)` or `("unknown", None)`.

- [x] 1.3 Implement `_parse_claude_md(repo_path: Path) -> list[str] | None` in `profiler.py`. Read `repo_path / "CLAUDE.md"`, find the first heading matching `^## build (?:&|and) test` (case-insensitive regex), extract content until the next `## ` heading or EOF, parse fenced code blocks (lines between ` ``` ` delimiters), collect non-empty non-comment lines as commands. Strip inline comments (everything after ` # ` with a leading space) from extracted command lines and trim whitespace. Lines starting with `#` are full comment lines and should be excluded. Return `None` if file missing, heading not found, or no commands extracted.

- [x] 1.4 Implement `_detect_python_commands(repo_path: Path) -> list[str]` in `profiler.py`. Parse `repo_path / "pyproject.toml"` with `tomllib`. Check for `[tool.pytest]` or `[tool.pytest.ini_options]` to include `uv run pytest -v`. Check for `[tool.ruff]` to include `uv run ruff check .` and `uv run ruff format --check .`. Check for `[tool.mypy]` to include `uv run mypy src/`. Return only commands for tools that have configuration.

- [x] 1.5 Implement `_detect_js_commands(repo_path: Path) -> list[str]` in `profiler.py`. Parse `repo_path / "package.json"` with `json.loads`. Check `scripts` object for `test` (-> `npm test`), `lint` (-> `npm run lint`), `format:check` or `format` (-> `npm run format:check`). Check if `tsconfig.json` exists for `npx tsc --noEmit`. Return only commands for detected scripts/tools.

- [x] 1.6 Implement `_detect_convention_commands(ecosystem: str, repo_path: Path) -> list[str]` in `profiler.py`. Dispatch to ecosystem-specific detectors: `python` -> `_detect_python_commands`, `javascript` -> `_detect_js_commands`. For `rust`, return `["cargo test", "cargo clippy -- -D warnings", "cargo fmt -- --check"]`. For `go`, return `["go test ./...", "golangci-lint run", "gofmt -l ."]`. For `make`, return `["make test"]` if `Makefile` contains a `test` target (check with regex `^test:`). For `ruby`, return `["bundle exec rake test", "bundle exec rubocop"]`. For unknown ecosystems, return `[]`.

- [x] 1.7 Implement the public `profile_repo(repo_path: Path) -> RepoProfile` function in `profiler.py`. First call `_parse_claude_md`. If commands found, return `RepoProfile(ecosystem=detected_ecosystem, eval_commands=commands, source="claude-md", marker_file="CLAUDE.md")`. Otherwise call `_detect_ecosystem` then `_detect_convention_commands`. If commands found, return with `source="convention"`. If no commands, return with `eval_commands=BOOTSTRAP_EVAL_COMMANDS` and `source="fallback"`.

## 2. Unit Tests for Profiler

- [x] 2.1 Create `tests/test_profiler.py`. Add test class `TestDetectEcosystem` with tests for: pyproject.toml detected as python, package.json as javascript, Cargo.toml as rust, go.mod as go, Makefile as make, no markers returns unknown, multiple markers returns highest priority. Use `tmp_path` fixture to create marker files.

- [x] 2.2 Add test class `TestParseClaudeMd` with tests for: extracts commands from `## Build & Test` section, extracts from `## Build and Test` (alternate heading), ignores comment lines in code blocks, ignores empty lines, returns None when no CLAUDE.md, returns None when heading not found, returns None when code block is empty, stops at next `## ` heading.

- [x] 2.3 Add test class `TestDetectPythonCommands` with tests for: all tools configured returns 4 commands, only pytest configured returns 1 command, no tools configured returns empty list, malformed TOML returns empty list (caught exception).

- [x] 2.4 Add test class `TestDetectJsCommands` with tests for: test and lint scripts detected, no scripts key returns empty, tsconfig.json present adds tsc command.

- [x] 2.5 Add test class `TestProfileRepo` with tests for: CLAUDE.md takes precedence over pyproject.toml, Python convention detection, fallback when nothing detected, source field is correct for each path, profile is JSON-serializable via `.model_dump_json()`.

## 3. Pipeline Integration

- [x] 3.1 In `src/action_harness/pipeline.py`, import `profile_repo` and `RepoProfile` from `profiler`. In `run_pipeline` (NOT `_run_pipeline_inner`), compute `profile = profile_repo(repo)` wrapped in try/except that logs a warning and falls back to `RepoProfile(ecosystem="unknown", eval_commands=BOOTSTRAP_EVAL_COMMANDS, source="fallback")`. Compute the profile BEFORE calling `_run_pipeline_inner`.

- [x] 3.2 Add `eval_commands: list[str]` as a new parameter to `_run_pipeline_inner`. Pass `profile.eval_commands` from `run_pipeline`. In the eval call inside `_run_pipeline_inner`, pass `eval_commands=eval_commands` to `run_eval`.

- [x] 3.3 In `src/action_harness/models.py`, import `RepoProfile` from `action_harness.profiler`. Add an optional `profile` field to `RunManifest`: `profile: RepoProfile | None = None`.

- [x] 3.4 In `_build_manifest` in `pipeline.py`, accept a `profile: RepoProfile | None` parameter and set it on the manifest. Pass `profile` from `run_pipeline` (where it is already computed in task 3.1) directly to `_build_manifest`.

- [x] 3.5 In `src/action_harness/cli.py`, in the `run` command's dry-run branch, replace the hardcoded `BOOTSTRAP_EVAL_COMMANDS` loop with a call to `profile_repo(repo)` and display `profile.eval_commands` along with `profile.ecosystem` and `profile.source`.

## 4. Integration Tests

- [x] 4.1 In `tests/test_profiler.py`, add an integration test `test_profile_action_harness_repo` that calls `profile_repo(Path(".").resolve())` on the actual action-harness repo and asserts: ecosystem is `"python"`, source is `"claude-md"` (since this repo has CLAUDE.md with Build & Test), eval_commands contains `"uv run pytest -v"`.

- [x] 4.2 In `tests/test_cli.py`, update or add a test for `--dry-run` output that verifies it shows detected ecosystem and source instead of only hardcoded commands.

## 5. Self-Validation

- [x] 5.1 Run `uv run pytest tests/test_profiler.py -v` and verify all profiler tests pass.
- [x] 5.2 Run `uv run pytest -v` and verify no existing tests are broken.
- [x] 5.3 Run `uv run ruff check .` and verify no lint errors.
- [x] 5.4 Run `uv run ruff format --check .` and verify no formatting issues.
- [x] 5.5 Run `uv run mypy src/` and verify no type errors.
- [x] 5.6 Run `action-harness run --change repo-profiling --repo . --dry-run` and verify the output shows detected ecosystem, source, and eval commands.
