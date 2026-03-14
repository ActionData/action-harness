## Context

The harness evaluator currently uses `BOOTSTRAP_EVAL_COMMANDS` — a hardcoded list of four Python commands (pytest, ruff, mypy). This works for self-hosting but prevents the harness from operating on any other repo. The `workspace-management` change (in the bootstrap backlog) will enable cloning external repos, but without repo profiling those repos will fail eval immediately because the wrong commands are run.

The profiler needs to be deterministic (no LLM calls), fast (runs once per pipeline), and safe (fallback to known-good defaults).

## Goals / Non-Goals

**Goals:**
- Detect the language ecosystem and eval commands for a target repo automatically.
- Support Python, JavaScript/TypeScript, Rust, Go, and Makefile-based projects at launch.
- Prefer explicit CLAUDE.md instructions over convention-based detection.
- Integrate cleanly into the existing pipeline without changing the eval runner's interface beyond accepting a command list (which it already does via `eval_commands` parameter).
- Record the profile in the run manifest for observability.

**Non-Goals:**
- Monorepo support (detecting multiple ecosystems in subdirectories). Single ecosystem per repo for now.
- Detecting CI configuration (`.github/workflows/*.yml`). CI is a separate signal.
- Auto-generating CLAUDE.md for repos that lack one. That is a separate capability.
- Deep dependency analysis (parsing lock files, detecting specific library versions).
- Supporting ecosystems beyond the initial set. The design allows extension but only the listed ecosystems ship in this change.

## Decisions

### D1: CLAUDE.md overrides convention detection

**Decision**: When a `CLAUDE.md` file exists with a `## Build & Test` section containing fenced code blocks, those commands are used directly. Convention-based detection is skipped entirely.

**Rationale**: CLAUDE.md is already the canonical source of build instructions for Claude Code. Repos that have invested in writing CLAUDE.md have the most accurate commands. Convention detection is a best-guess; explicit instructions are authoritative.

**Alternative considered**: Merge CLAUDE.md commands with convention-detected commands. Rejected because merging creates ambiguity about duplicates and ordering, and CLAUDE.md already captures the author's intended command set.

### D2: Priority-ordered marker file scanning

**Decision**: Scan for marker files in a fixed priority order: `pyproject.toml` > `setup.py` > `package.json` > `Cargo.toml` > `go.mod` > `Makefile` > `Gemfile`. First match wins.

**Rationale**: A repo may have both `Makefile` and `pyproject.toml` (many Python projects do). The ecosystem-specific marker is more informative than the generic one. The priority order reflects specificity — language-specific markers before generic build tools.

**Alternative considered**: Detect all markers and return a list of ecosystems. Rejected as over-engineering for the initial version — the eval runner takes a single command list, not per-ecosystem lists.

### D3: Validate tool presence in config files

**Decision**: For Python, parse `pyproject.toml` to check whether `[tool.pytest]`, `[tool.ruff]`, and `[tool.mypy]` sections exist before including those commands. For JavaScript, check `package.json` `scripts` for matching entries.

**Rationale**: Including commands for tools that aren't configured causes eval failures that waste retry budget. A Python repo without mypy shouldn't have `uv run mypy src/` in its eval commands.

**Alternative considered**: Include all conventional commands and let eval failures trigger retries. Rejected because it burns retries on infrastructure misconfiguration rather than code quality issues.

### D4: RepoProfile as a Pydantic model in profiler.py

**Decision**: Define `RepoProfile` in `src/action_harness/profiler.py` (not in `models.py`). Import it into `models.py` for the `RunManifest` field.

**Rationale**: The profiler module is self-contained — it has the detection logic and the data model. Keeping them together makes the module independently testable. The model is imported into `models.py` only for the manifest type annotation, avoiding circular imports since `profiler.py` does not import from `models.py`.

**Alternative considered**: Define `RepoProfile` in `models.py` alongside other models. Acceptable, but would create a dependency from `profiler.py` to `models.py` that isn't needed. The profiler has no other reason to import from models.

### D5: Profile computed in pipeline.py, passed to run_eval

**Decision**: Call `profile_repo(repo_path)` in `run_pipeline` (not `_run_pipeline_inner`) before the try block. Pass `profile.eval_commands` to `_run_pipeline_inner` as a new `eval_commands: list[str]` parameter, which threads it to `run_eval`. Pass `profile` directly to `_build_manifest`.

**Rationale**: The repo root represents the canonical, unmodified state. Worktrees are created from it and may diverge during worker implementation. Profiling the stable source avoids re-detection on retry. Computing the profile in `run_pipeline` (where the manifest is built) avoids the need to return the profile from `_run_pipeline_inner`. The `run_eval` function already accepts `eval_commands: list[str] | None`, so no eval signature change is needed.

### D6: CLAUDE.md parsing strategy

**Decision**: Read CLAUDE.md as text. Find the first `## Build & Test` or `## Build and Test` heading (case-insensitive match via regex `^## build (?:&|and) test`). Extract content until the next `## ` heading or EOF. Within that section, find fenced code blocks (` ``` ` delimiters). Extract non-empty, non-comment lines from code blocks as commands.

**Rationale**: This is the exact structure used by action-harness's own CLAUDE.md and is the convention Claude Code users follow. The parser is simple (regex + line iteration, no markdown AST library) and handles the common case.

**Alternative considered**: Use a markdown parsing library (e.g., `markdown-it-py`). Rejected to avoid adding a dependency for a simple extraction task.

### D7: Fallback is silent with a log warning

**Decision**: If the profiler raises an exception or detects nothing, `_run_pipeline_inner` catches the error, logs a warning via `typer.echo(..., err=True)`, and uses `BOOTSTRAP_EVAL_COMMANDS`. The pipeline continues.

**Rationale**: Profiling failure should not block the pipeline. The bootstrap commands are a safe default for the harness's own repo, and for unknown repos they will fail at eval time with clear error messages (command not found), which is better than aborting before trying.

## Risks / Trade-offs

**[Risk] Convention commands may not match repo's actual setup** (e.g., a Python repo uses `poetry` instead of `uv`).
Mitigation: CLAUDE.md override takes precedence for any repo with explicit instructions. Convention detection is a best-effort starting point. Future work could add more package manager detection (poetry, pip, pdm).

**[Risk] CLAUDE.md parsing is fragile** — non-standard formatting could cause missed commands.
Mitigation: The parser handles the common case (`## Build & Test` + fenced blocks). If parsing fails, convention detection provides a second chance. If both fail, bootstrap fallback kicks in.

**[Risk] pyproject.toml parsing could fail on malformed TOML.**
Mitigation: Use `tomllib` (stdlib in Python 3.11+) with try/except. Parse failure falls through to fallback.

**[Trade-off] Single ecosystem detection limits monorepo support.**
Accepted: Monorepos are out of scope. The design extends naturally (return a list of profiles) when needed.

**[Trade-off] No runtime validation that detected commands actually exist as executables.**
Accepted: Checking `shutil.which` for every command adds complexity and may not reflect the worktree's virtualenv. Let eval failures handle missing tools naturally with clear error messages.
