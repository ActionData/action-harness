## Why

The harness currently hardcodes `BOOTSTRAP_EVAL_COMMANDS` in `evaluator.py` — four Python-specific commands (pytest, ruff check, ruff format, mypy). This means the pipeline only works on Python repos that use this exact toolchain. Before `workspace-management` can target non-Python repos (or even Python repos with different tooling), the harness needs to discover what eval commands a repo supports automatically.

Repo profiling scans the target repository once before the pipeline starts, detects the language ecosystem, build system, and available quality tools, and produces a structured profile that the evaluator consumes instead of the hardcoded constant.

## What Changes

- Add a `profiler` module that scans a repository root for ecosystem markers (pyproject.toml, package.json, Cargo.toml, go.mod, Makefile) and CLAUDE.md build instructions.
- Introduce a `RepoProfile` Pydantic model that captures detected language, test command, lint command, format command, and type check command.
- Integrate profiling into the pipeline: profile the repo before the first eval, pass detected commands to `run_eval`.
- Replace `BOOTSTRAP_EVAL_COMMANDS` usage in `cli.py` (dry-run output) and `pipeline.py` (eval dispatch) with profile-derived commands.
- Fall back to `BOOTSTRAP_EVAL_COMMANDS` when detection finds nothing (safe default for the harness's own repo).

## Capabilities

### New Capabilities
- `repo-profiling`: Detect language ecosystem, build system, and eval commands from a target repository's file markers and documentation.

### Modified Capabilities
_(none — no existing specs to modify)_

## Impact

- **New file**: `src/action_harness/profiler.py` — detection logic and `RepoProfile` model.
- **New file**: `tests/test_profiler.py` — unit tests for detection.
- **Modified**: `src/action_harness/pipeline.py` — call profiler before eval, pass commands through.
- **Modified**: `src/action_harness/cli.py` — dry-run shows detected commands instead of hardcoded list.
- **Modified**: `src/action_harness/models.py` — add `RepoProfile` or import it.
- **Modified**: `src/action_harness/evaluator.py` — `BOOTSTRAP_EVAL_COMMANDS` remains as fallback but is no longer the primary source of eval commands.
- **Dependency**: Pydantic (already in use). No new dependencies.
