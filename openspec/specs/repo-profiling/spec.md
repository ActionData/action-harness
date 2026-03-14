# repo-profiling Specification

## Purpose
TBD - created by archiving change repo-profiling. Update Purpose after archive.
## Requirements
### Requirement: Detect language ecosystem from file markers

The profiler SHALL detect the primary language ecosystem of a repository by scanning for marker files at the repository root. The following markers SHALL be recognized:

| Marker file       | Ecosystem  |
|-------------------|------------|
| `pyproject.toml`  | python     |
| `setup.py`        | python     |
| `package.json`    | javascript |
| `Cargo.toml`      | rust       |
| `go.mod`          | go         |
| `Makefile`        | make       |
| `Gemfile`         | ruby       |

When multiple markers are present, the profiler SHALL select the first match in the priority order listed above.

When no marker is found, the ecosystem SHALL be `"unknown"`.

#### Scenario: Python repo with pyproject.toml
- **WHEN** the repository root contains a `pyproject.toml` file
- **THEN** the detected ecosystem SHALL be `"python"`

#### Scenario: JavaScript repo with package.json
- **WHEN** the repository root contains a `package.json` file but no `pyproject.toml`
- **THEN** the detected ecosystem SHALL be `"javascript"`

#### Scenario: Rust repo with Cargo.toml
- **WHEN** the repository root contains a `Cargo.toml` file but no higher-priority markers
- **THEN** the detected ecosystem SHALL be `"rust"`

#### Scenario: Go repo with go.mod
- **WHEN** the repository root contains a `go.mod` file but no higher-priority markers
- **THEN** the detected ecosystem SHALL be `"go"`

#### Scenario: Multiple markers present
- **WHEN** the repository root contains both `pyproject.toml` and `package.json`
- **THEN** the detected ecosystem SHALL be `"python"` (higher priority)

#### Scenario: No markers found
- **WHEN** the repository root contains none of the recognized marker files
- **THEN** the detected ecosystem SHALL be `"unknown"`

### Requirement: Detect eval commands from ecosystem conventions

The profiler SHALL produce a list of eval commands based on the detected ecosystem. For each ecosystem, the profiler SHALL map to conventional tool commands:

| Ecosystem  | Test              | Lint                  | Format                      | Type check        |
|------------|-------------------|-----------------------|-----------------------------|-------------------|
| python     | `uv run pytest -v`| `uv run ruff check .` | `uv run ruff format --check .`| `uv run mypy src/`|
| javascript | `npm test`        | `npm run lint`        | `npm run format:check`      | `npx tsc --noEmit`|
| rust       | `cargo test`      | `cargo clippy -- -D warnings` | `cargo fmt -- --check` | _(none)_     |
| go         | `go test ./...`   | `golangci-lint run`   | `gofmt -l .`                | _(none)_          |
| ruby       | `bundle exec rake test` | `bundle exec rubocop` | _(none)_              | _(none)_          |
| make       | `make test`       | `make lint`           | _(none)_                    | _(none)_          |

The profiler SHALL only include commands for tools that appear to be configured in the repo. For Python, the profiler SHALL check `pyproject.toml` for `[tool.pytest]`, `[tool.ruff]`, and `[tool.mypy]` sections. For JavaScript, the profiler SHALL check `package.json` for matching script names in the `scripts` object.

Commands that are not detected SHALL be omitted from the profile (not included as empty strings).

#### Scenario: Python repo with all tools configured
- **WHEN** the repo has `pyproject.toml` containing `[tool.pytest.ini_options]`, `[tool.ruff]`, and `[tool.mypy]` sections
- **THEN** the eval commands list SHALL contain commands for test, lint, format, and type check

#### Scenario: Python repo with only pytest configured
- **WHEN** the repo has `pyproject.toml` containing `[tool.pytest.ini_options]` but no `[tool.ruff]` or `[tool.mypy]`
- **THEN** the eval commands list SHALL contain only the test command

#### Scenario: JavaScript repo with test and lint scripts
- **WHEN** the repo has `package.json` with `"test"` and `"lint"` in `scripts`
- **THEN** the eval commands list SHALL contain `npm test` and `npm run lint`

#### Scenario: Rust repo
- **WHEN** the repo has `Cargo.toml`
- **THEN** the eval commands list SHALL contain `cargo test`, `cargo clippy -- -D warnings`, and `cargo fmt -- --check`

#### Scenario: Go repo
- **WHEN** the repo has `go.mod`
- **THEN** the eval commands list SHALL contain `go test ./...`, `golangci-lint run`, and `gofmt -l .`

#### Scenario: Ruby repo
- **WHEN** the repo has `Gemfile`
- **THEN** the eval commands list SHALL contain `bundle exec rake test` and `bundle exec rubocop`

### Requirement: Parse CLAUDE.md for explicit build commands

The profiler SHALL check for a `CLAUDE.md` file at the repository root. If present, it SHALL scan for a section matching the heading pattern `## Build & Test` or `## Build and Test` (case-insensitive). When found, the profiler SHALL extract code-fenced command blocks from that section and use them as the eval commands, overriding ecosystem-convention detection.

#### Scenario: CLAUDE.md with Build & Test section
- **WHEN** the repo contains a `CLAUDE.md` with a `## Build & Test` section containing a fenced code block with commands
- **THEN** the profiler SHALL use those commands as eval commands, overriding convention-based detection

#### Scenario: CLAUDE.md without Build & Test section
- **WHEN** the repo contains a `CLAUDE.md` without a `## Build & Test` heading
- **THEN** the profiler SHALL fall back to ecosystem-convention detection

#### Scenario: No CLAUDE.md present
- **WHEN** the repo does not contain a `CLAUDE.md` file
- **THEN** the profiler SHALL use ecosystem-convention detection

#### Scenario: CLAUDE.md commands take precedence
- **WHEN** the repo has both a `CLAUDE.md` with build commands and a `pyproject.toml` with tool configurations
- **THEN** the CLAUDE.md commands SHALL be used, not the convention-based commands

#### Scenario: CLAUDE.md with inline comments
- **WHEN** a code block command contains an inline comment (e.g., `uv sync  # install dependencies`)
- **THEN** the profiler SHALL strip the inline comment and extract only the command portion (`uv sync`)

#### Scenario: CLAUDE.md with multiple code blocks
- **WHEN** the Build & Test section contains multiple fenced code blocks
- **THEN** the profiler SHALL extract commands from all code blocks in order

### Requirement: Produce a RepoProfile model

The profiler SHALL produce a `RepoProfile` Pydantic model with the following fields:

| Field           | Type           | Description                                      |
|-----------------|----------------|--------------------------------------------------|
| `ecosystem`     | `str`          | Detected ecosystem identifier (e.g., `"python"`) |
| `eval_commands` | `list[str]`    | Ordered list of eval commands to run              |
| `source`        | `str`          | How commands were determined: `"claude-md"`, `"convention"`, or `"fallback"` |
| `marker_file`   | `str \| None`  | The marker file that triggered detection          |

The `RepoProfile` SHALL be serializable to JSON for inclusion in the run manifest.

#### Scenario: Profile from CLAUDE.md
- **WHEN** the profiler detects commands from CLAUDE.md
- **THEN** the `source` field SHALL be `"claude-md"` and `eval_commands` SHALL contain the parsed commands

#### Scenario: Profile from convention
- **WHEN** the profiler detects commands from ecosystem conventions
- **THEN** the `source` field SHALL be `"convention"` and `marker_file` SHALL name the detected marker

#### Scenario: Fallback profile
- **WHEN** detection finds no ecosystem markers and no CLAUDE.md build section
- **THEN** the `source` field SHALL be `"fallback"` and `eval_commands` SHALL equal `BOOTSTRAP_EVAL_COMMANDS`

#### Scenario: JSON serialization
- **WHEN** the `RepoProfile` is serialized with `.model_dump_json()`
- **THEN** the output SHALL be valid JSON containing all four fields

### Requirement: Profile is computed once per pipeline run

The profiler SHALL be invoked once at the start of the pipeline, before the first worker dispatch. The resulting `RepoProfile` SHALL be passed to `run_eval` for the duration of the pipeline run (including retries). The profiler SHALL NOT be invoked again during retries.

#### Scenario: Single profiling call across retries
- **WHEN** the pipeline runs with 2 retries
- **THEN** the profiler SHALL be called exactly once, and all 3 eval invocations SHALL use the same profile

#### Scenario: Profile is available before first eval
- **WHEN** the pipeline starts
- **THEN** the repo SHALL be profiled after worktree creation and before the first worker dispatch

### Requirement: Fallback to bootstrap commands on detection failure

When the profiler detects no ecosystem and finds no CLAUDE.md build section, the `eval_commands` SHALL fall back to `BOOTSTRAP_EVAL_COMMANDS`. This ensures the harness continues to work on its own repo without configuration.

#### Scenario: Unknown ecosystem with no CLAUDE.md
- **WHEN** the repo has no recognized marker files and no CLAUDE.md
- **THEN** `eval_commands` SHALL equal `BOOTSTRAP_EVAL_COMMANDS`

#### Scenario: Profiler exception
- **WHEN** the profiler raises an unexpected exception during scanning
- **THEN** the pipeline SHALL catch the exception, log a warning, and use `BOOTSTRAP_EVAL_COMMANDS` as the eval commands

### Requirement: Profile included in run manifest

The `RunManifest` SHALL include a `profile` field containing the `RepoProfile` used for the run. This enables post-run analysis of what detection strategy was used.

#### Scenario: Manifest contains profile
- **WHEN** a pipeline run completes (success or failure)
- **THEN** the `RunManifest` JSON SHALL contain a `profile` object with `ecosystem`, `eval_commands`, `source`, and `marker_file` fields

#### Scenario: Manifest with fallback profile
- **WHEN** detection falls back to bootstrap commands
- **THEN** the manifest `profile.source` SHALL be `"fallback"`

