# Review Agents Tasks

Prerequisites: these tasks assume `structured-logging` has NOT been implemented yet. If it has, also pass the `EventLogger` to review dispatch functions and emit `review.dispatched` / `review.completed` events.

## Group 0: Shared Utilities

- [x] 0.1 Extract `_extract_json_block` from `src/action_harness/openspec_reviewer.py` into a shared module `src/action_harness/parsing.py`. Update `openspec_reviewer.py` to import from there. This function is needed by both the openspec reviewer and the review agents.

## Group 1: Models

- [x] 1.1 In `src/action_harness/models.py`, add `ReviewFinding` model with fields: `title: str`, `file: str`, `line: int | None = None`, `severity: Literal["critical", "high", "medium", "low"]`, `description: str`, `agent: str`.
- [x] 1.2 In `src/action_harness/models.py`, add `ReviewResult(StageResult)` model with fields: `stage: Literal["review"] = "review"`, `agent_name: str`, `findings: list[ReviewFinding] = []`, `cost_usd: float | None = None`.
- [x] 1.3 In `src/action_harness/models.py`, add `ReviewResult` to the `StageResultUnion` discriminated union.
- [x] 1.4 In `tests/test_models.py`, add tests for `ReviewFinding` and `ReviewResult`: construction, serialization, deserialization, inclusion in `RunManifest.stages`, and round-trip through JSON.

## Group 2: Review Agent Dispatch

- [x] 2.1 Create `src/action_harness/review_agents.py` with the following functions (stubs initially): `build_review_prompt(agent_name: str, pr_number: int) -> str`, `dispatch_single_review(agent_name: str, pr_number: int, worktree_path: Path, ...) -> ReviewResult`, `dispatch_review_agents(pr_number: int, worktree_path: Path, ...) -> list[ReviewResult]`, `parse_review_findings(raw_output: str, agent_name: str, duration: float) -> ReviewResult`, `triage_findings(results: list[ReviewResult]) -> bool` (returns True if fix retry needed), `format_review_feedback(results: list[ReviewResult]) -> str`.
- [x] 2.2 Implement `build_review_prompt(agent_name: str, pr_number: int) -> str` that returns a system prompt. For each agent name ("bug-hunter", "test-reviewer", "quality-reviewer"), the prompt SHALL contain the review instructions matching the agent definitions in `~/.claude/agents/{agent_name}.md`, plus a suffix instructing the agent to output a JSON block with structure `{"findings": [{"title": str, "file": str, "line": int|null, "severity": str, "description": str}], "summary": str}`. The prompt content should be hardcoded in the module (not read from `~/.claude/agents/` at runtime).
- [x] 2.3 Implement `dispatch_single_review(agent_name: str, pr_number: int, worktree_path: Path, max_turns: int = 50, model: str | None = None, effort: str | None = None, max_budget_usd: float | None = None, permission_mode: str = "default", verbose: bool = False) -> ReviewResult`. This function SHALL: build a `claude -p` command with the system prompt from `build_review_prompt`, a user prompt of `"Review PR #{pr_number}"`, `--output-format json`, `--max-turns`, and optional `--model`/`--effort`/`--max-budget-usd` flags. Run via `subprocess.run` with `cwd=worktree_path`, `capture_output=True`, `text=True`. Parse output with `parse_review_findings`. Log to stderr via `typer.echo` with prefix `[review:{agent_name}]`.
- [x] 2.4 Implement `parse_review_findings(raw_output: str, agent_name: str, duration: float) -> ReviewResult`. Parse the Claude CLI JSON envelope (`json.loads` the output, get `result` field). Extract the JSON block from the result text using the same `_extract_json_block` pattern from `openspec_reviewer.py` (import it or duplicate it into a shared utility). Map each finding dict to a `ReviewFinding(agent=agent_name, ...)`. Return `ReviewResult(success=True, agent_name=agent_name, findings=[...], duration_seconds=duration, cost_usd=...)`. On parse failure, return `ReviewResult(success=False, agent_name=agent_name, error="...", duration_seconds=duration)`.
- [x] 2.5 Implement `dispatch_review_agents(pr_number: int, worktree_path: Path, max_turns: int = 50, model: str | None = None, effort: str | None = None, max_budget_usd: float | None = None, permission_mode: str = "default", verbose: bool = False) -> list[ReviewResult]`. Use `concurrent.futures.ThreadPoolExecutor(max_workers=3)` to dispatch all three agents in parallel via `dispatch_single_review`. Collect all results. Log total duration.
- [x] 2.6 Implement `triage_findings(results: list[ReviewResult]) -> bool`. Return `True` if any `ReviewFinding` across all results has severity "critical" or "high". Return `False` otherwise (including when all results have `success=False`).
- [x] 2.7 Implement `format_review_feedback(results: list[ReviewResult]) -> str`. Format high/critical findings as structured markdown feedback. Include: finding title, file, line, severity, description, agent name. Add header "## Review Agent Findings" and footer "Fix the high/critical issues above and re-run eval to verify."

## Group 3: Tests for Review Agent Module

- [x] 3.1 Create `tests/test_review_agents.py`. Add unit tests for `build_review_prompt`: verify it returns a non-empty string for each of the three agent names, verify the prompt contains JSON output instructions, verify it raises or returns a sensible error for unknown agent names.
- [x] 3.2 Add unit tests for `parse_review_findings`: test with valid JSON containing findings, test with empty findings list, test with unparseable output (returns error result), test that `agent` field is set correctly on each `ReviewFinding`.
- [x] 3.3 Add unit tests for `triage_findings`: test returns `True` when a "critical" finding exists, `True` for "high", `False` for only "medium"/"low", `False` for empty findings, `False` when all results have `success=False`.
- [x] 3.4 Add unit tests for `format_review_feedback`: test that output contains finding titles and file references, test that only high/critical findings are included, test empty input produces a no-findings message.
- [x] 3.5 Add unit tests for `dispatch_single_review` with mocked `subprocess.run`: verify the `claude` CLI command is constructed correctly (includes `--output-format json`, `--max-turns`, system prompt), verify `cwd` is set to `worktree_path`, verify the result is parsed into a `ReviewResult`.
- [x] 3.6 Add unit tests for `dispatch_review_agents` with mocked `dispatch_single_review`: verify three agents are dispatched, verify results are collected, verify parallel execution (all three calls happen regardless of individual failures).

## Group 4: Pipeline Integration

- [ ] 4.1 In `pipeline.py`, import `dispatch_review_agents`, `triage_findings`, `format_review_feedback` from `action_harness.review_agents`. Import `ReviewResult` from `action_harness.models`.
- [ ] 4.2 In `pipeline.py`, add a `_run_review_agents` function that: (a) extracts the PR number from `pr_result.pr_url` (parse the URL to get the number), (b) calls `dispatch_review_agents(pr_number, worktree_path, ...)`, (c) appends each `ReviewResult` to `stages`, (d) calls `_post_review_comment(worktree_path, pr_result.pr_url, review_results, verbose)`, (e) calls `triage_findings(review_results)` to determine if fix retry is needed, (f) returns the list of `ReviewResult`.
- [ ] 4.3 In `pipeline.py`, add a `_post_review_comment` function that formats review findings into a PR comment body (grouped by agent, with severity/title/file/line for each finding) and posts it via `gh pr comment`. If no findings, post "All review agents passed with no findings."
- [ ] 4.4 In `pipeline.py`, add a `_run_review_fix_retry` function that: (a) formats review feedback via `format_review_feedback`, (b) re-dispatches the code worker with the feedback string, (c) re-runs eval, (d) if eval passes, pushes the new commits to the PR branch via `git push`, (e) posts a PR comment via `gh pr comment` noting findings were addressed and new commits pushed, (f) appends worker and eval results to `stages`, (g) returns success/failure.
- [ ] 4.5 In `_run_pipeline_inner`, insert the review-agents stage between PR creation and OpenSpec review. After `pr_result` is confirmed successful: call `_run_review_agents(...)`. If triage returns True (high/critical findings), call `_run_review_fix_retry(...)`. Then proceed to `_run_openspec_review(...)` as before.
- [ ] 4.6 In `pipeline.py`, update `_build_manifest` to sum `cost_usd` from `ReviewResult` entries in addition to `WorkerResult` entries. Parse `cost_usd` from the Claude CLI JSON envelope via `output_data.get('cost_usd')`.
- [ ] 4.7 Update `review_agents.py` to import `_extract_json_block` from `src/action_harness/parsing.py` (created in task 0.1). Update `openspec_reviewer.py` to also import from there.
- [ ] 4.8 In `cli.py`, add `--skip-review` flag (bool, default False). When set, skip the review-agents stage. Pass through to `run_pipeline` and `_run_pipeline_inner`. This allows debugging, dry runs, or cost-conscious runs without the 3 additional Claude Code dispatches.

## Group 5: Integration Tests

- [ ] 5.1 In `tests/test_integration.py` (or a new `tests/test_pipeline_review.py`), add a test that mocks `subprocess.run` to simulate the full pipeline with review agents. Verify: three `ReviewResult` entries appear in the manifest stages, they appear after `PrResult` and before `OpenSpecReviewResult`.
- [ ] 5.2 Add a test for the fix-retry path: mock review agents to return a high-severity finding, verify the pipeline re-dispatches the worker with feedback, verify an additional `WorkerResult` and `EvalResult` appear in the manifest.
- [ ] 5.3 Add a test for the no-retry path: mock review agents to return only medium/low findings, verify the pipeline proceeds directly to OpenSpec review without additional worker dispatch.

## Self-Validation

Run the following commands to validate the implementation:

```bash
# All tests pass (including new review agent tests)
uv run pytest -v

# Lint clean
uv run ruff check .

# Format clean
uv run ruff format --check .

# Type check clean
uv run mypy src/

# Verify the new module exists and exports expected functions
python -c "from action_harness.review_agents import dispatch_review_agents, triage_findings, format_review_feedback, parse_review_findings, build_review_prompt; print('imports ok')"

# Verify models are updated
python -c "from action_harness.models import ReviewResult, ReviewFinding, StageResultUnion; print('models ok')"

# Verify ReviewResult round-trips through JSON in a manifest
python -c "
from action_harness.models import ReviewResult, ReviewFinding, RunManifest
import json
f = ReviewFinding(title='test', file='foo.py', severity='high', description='desc', agent='bug-hunter')
r = ReviewResult(success=True, agent_name='bug-hunter', findings=[f])
m = RunManifest(change_name='test', repo_path='.', started_at='2024-01-01', completed_at='2024-01-01', success=True, stages=[r], total_duration_seconds=0)
j = m.model_dump_json()
m2 = RunManifest.model_validate_json(j)
assert isinstance(m2.stages[0], ReviewResult)
assert m2.stages[0].findings[0].title == 'test'
print('round-trip ok')
"
```

### Human Prerequisites

None. All validation steps are fully automated.
