## 1. Assessment Models [no dependencies]

- [x] 1.1 Create `src/action_harness/assessment.py` with Pydantic models: `Gap` (severity: Literal["high", "medium", "low"], finding: str, category: str, proposal_name: str | None), `CIMechanicalSignals` (ci_exists: bool, triggers_on_pr: bool, runs_tests: bool, runs_lint: bool, runs_typecheck: bool, runs_format_check: bool, branch_protection: bool | None), `TestabilityMechanicalSignals` (test_framework_configured: bool, test_files: int, test_functions: int, coverage_configured: bool), `ContextMechanicalSignals` (claude_md: bool, readme: bool, harness_md: bool, agents_md: bool, type_annotations_present: bool, docstrings_present: bool), `ToolingMechanicalSignals` (package_manager: bool, lockfile_present: bool, lockfile: str | None, mcp_configured: bool, skills_present: bool, docker_configured: bool, cli_tools_available: bool), `ObservabilityMechanicalSignals` (structured_logging_lib: bool, health_endpoint: bool, metrics_lib: bool, tracing_lib: bool, log_level_configurable: bool), `IsolationMechanicalSignals` (git_repo: bool, lockfile_present: bool, env_example_present: bool, no_committed_secrets: bool, reproducible_build: bool), `CategoryScore` (score: int, mechanical_signals: CIMechanicalSignals | TestabilityMechanicalSignals | ContextMechanicalSignals | ToolingMechanicalSignals | ObservabilityMechanicalSignals | IsolationMechanicalSignals, agent_assessment: str | None, gaps: list[Gap]), `AssessmentReport` (overall_score: int, categories: dict[str, CategoryScore], proposals: list[Gap], repo_path: str, timestamp: str, mode: Literal["base", "deep", "propose"])
- [x] 1.2 Add tests for model serialization: `AssessmentReport` roundtrip via `model_dump_json()` and `model_validate_json()` preserves all fields including nested `Gap.proposal_name` and `CategoryScore.score`. Overall_score computed as arithmetic mean of category scores.

## 2. Mechanical Scan — CI Workflow Parsing [depends: 1]

- [x] 2.1 Create `src/action_harness/ci_parser.py` with a `parse_github_actions(repo_path: Path) -> CIMechanicalSignals` function that parses `.github/workflows/*.yml` and returns typed signals
- [x] 2.2 Match CI step `run:` commands against known tool patterns (pytest, ruff, eslint, mypy, tsc, cargo test, cargo clippy, cargo fmt, etc.)
- [x] 2.3 Add tests for CI parsing: workflow with full checks, workflow with only test, workflow triggering on PR vs push-only, no workflows present, malformed YAML (skip file, log warning, continue processing other files)

## 3. Mechanical Scan — Lockfile and Test Structure [depends: 1]

- [x] 3.1 Create `src/action_harness/scanner.py` with `detect_lockfiles(repo_path: Path) -> tuple[bool, str | None]` that checks for uv.lock, package-lock.json, yarn.lock, pnpm-lock.yaml, Cargo.lock, go.sum, Gemfile.lock
- [x] 3.2 Add `analyze_test_structure(repo_path: Path, ecosystem: str) -> TestabilityMechanicalSignals` that counts test files and test functions by ecosystem pattern (Python: `test_*.py` / `def test_`, JS: `*.test.ts` / `it(`, Rust: `#[test]`). Check for coverage config (e.g., `[tool.coverage]` in pyproject.toml, `.nycrc`)
- [x] 3.3 Add tests for lockfile detection (present/absent) and test structure analysis (Python, JS, empty repo)

## 4. Mechanical Scan — Context and Tooling Markers [depends: 1]

- [x] 4.1 Add `detect_context_signals(repo_path: Path) -> ContextMechanicalSignals` that checks for CLAUDE.md, README.md/README, HARNESS.md, AGENTS.md. Sample a few source files for type annotations and docstrings.
- [x] 4.2 Add `detect_tooling_signals(repo_path: Path) -> ToolingMechanicalSignals` that checks for package manager markers (pyproject.toml, package.json, etc.), lockfiles, MCP configs in `.claude/mcp*.json`, skills in `.claude/commands/`, Docker files (Dockerfile, docker-compose.yml, compose.yml)
- [x] 4.3 Add `detect_observability_signals(repo_path: Path) -> ObservabilityMechanicalSignals` that checks for logging libs (structlog, logging config, winston, tracing crate), health endpoints (grep for `/health` or `/healthz`), metrics libs (prometheus_client, prom-client), tracing libs (opentelemetry)
- [x] 4.4 Add `detect_isolation_signals(repo_path: Path) -> IsolationMechanicalSignals` that checks for git repo, lockfile, .env.example, scans for potential committed secrets patterns, checks for reproducible build indicators
- [x] 4.5 Add tests for each detector: present/absent cases, graceful failure on unreadable files

## 5. GitHub API Checks [depends: 1]

- [x] 5.1 Add optional `check_branch_protection(repo_path: Path) -> bool | None` that calls `gh api repos/{owner}/{repo}/branches/{branch}/protection`. Return True if protected, False if not, None if gh is unavailable or unauthenticated.
- [x] 5.2 Add tests: mock gh command success, gh not available (returns None), gh auth error (returns None)

## 6. Scoring Logic [depends: 1, 2, 3, 4, 5]

- [x] 6.1 Create `src/action_harness/scoring.py` with `score_category(category: str, signals: BaseModel) -> CategoryScore` that computes a 0-100 score using the weighted sub-signal tables defined in the scoring spec
- [x] 6.2 Add `identify_gaps(category: str, signals: BaseModel) -> list[Gap]` that identifies gaps for sub-signals worth >= 15 points that are false/absent. Classify severity: >= 25 points = high, >= 15 = medium. Assign kebab-case `proposal_name` per gap.
- [x] 6.3 Add `compute_overall(categories: dict[str, CategoryScore]) -> int` that returns the arithmetic mean of category scores rounded to nearest integer
- [x] 6.4 Add tests: perfect repo = 100 per category, empty repo = 0, partial CI (exists + pr trigger + tests only) = 60, missing CLAUDE.md produces a high-severity gap with `proposal_name` `add-claude-md`, runs_format_check missing does NOT produce a gap (below threshold)

## 7. CLI Command — Base Mode [depends: 6]

- [x] 7.1 Add `harness assess` command to `cli.py` with `--repo` (required Path), `--deep` (flag), `--propose` (flag), `--json` (flag). If `--propose` is provided, set `deep=True` automatically (no error, no separate flag required).
- [x] 7.2 Base mode: call `profile_repo()` for ecosystem, run all mechanical scanners, compute scores via scoring module, print formatted terminal report with category names, numeric scores, and signal summaries. All diagnostic output to stderr.
- [x] 7.3 Add `--json` flag: when provided, output the full `AssessmentReport` JSON to stdout. All diagnostic/progress output goes to stderr.
- [x] 7.4 Add tests for CLI: `--help` output, base mode runs without error on a git repo, `--json` produces valid JSON to stdout with all six categories

## 8. Assessment Agent Dispatch (--deep) [depends: 7]

- [x] 8.1 Create `src/action_harness/assess_agent.py` with a function to build the assessment agent prompt: system prompt with scoring rubric and the expected JSON output schema (categories object with score_adjustment, rationale, gaps per category), user prompt with mechanical signals JSON
- [x] 8.2 Create `dispatch_readonly_worker(prompt: str, system_prompt: str, worktree_path: Path, ...) -> dict | None` function (separate from `dispatch_worker`) that dispatches Claude CLI with `--allowedTools "Read,Glob,Grep,Bash"`, does NOT call `count_commits_ahead`, and returns parsed JSON output or None on failure
- [x] 8.3 Merge agent results with mechanical scores: for each category, add `score_adjustment` to mechanical score (clamped to ±20), populate `agent_assessment` field with rationale, append agent-identified gaps to the category's gap list
- [x] 8.4 Add tests: mock agent dispatch, verify prompt contains mechanical signals JSON and output schema, verify JSON parsing of agent output, verify score clamping (adjustment > 20 gets clamped), verify graceful fallback to mechanical-only scores on agent failure

## 9. Gap Proposals (--propose) [depends: 8]

- [x] 9.1 For each gap with a `proposal_name`, run `openspec new change "<proposal_name>"` to scaffold the change directory
- [x] 9.2 Dispatch a spec-writer agent per gap with: gap finding, repo context (ecosystem, tools, CLAUDE.md contents), and instructions to write `proposal.md` for the new change
- [x] 9.3 Support parallel dispatch of spec-writer agents (subprocess concurrency)
- [x] 9.4 Report results: list generated proposals in terminal output, handle individual spec-writer failures without blocking others
- [x] 9.5 Add tests: mock spec-writer dispatch, verify openspec change directories created, verify failure isolation

## 10. Terminal Output Formatting [depends: 7]

- [x] 10.1 Format terminal output: each category on its own line with name, numeric score, and `████░░░░░░` style bar (10 blocks, each = 10 points). Below each category, list findings with severity labels.
- [x] 10.2 In `--deep` mode, include agent rationale below each category score
- [x] 10.3 In `--propose` mode, append a "Generated Proposals" section listing each proposal name and path

## 11. Validation [depends: all]

- [ ] 11.1 Run `harness assess --repo .` on the action-harness repo itself. Verify: exit code 0, output contains all six category names, overall score is an integer between 0 and 100, ci_guardrails reports `runs_tests: true`
- [ ] 11.2 Run full test suite (`uv run pytest -v`) and verify no regressions
- [ ] 11.3 Run lint and type checks (`uv run ruff check .` and `uv run mypy src/`)
