# Review Agents Design

## Architecture Overview

Review agents are Claude Code CLI dispatches that run in parallel after PR creation. They read the PR diff via `gh pr diff`, produce structured JSON findings, and the pipeline triages those findings to decide whether to re-dispatch the code worker for fixes.

```
PR created
  |
  +---> bug-hunter (Claude Code CLI) --+
  +---> test-reviewer (Claude Code CLI) --> collect findings
  +---> quality-reviewer (Claude Code CLI) --+
  |
  v
triage (deterministic, no LLM)
  |
  +-- high/critical findings --> fix worker --> eval --> push
  +-- medium/low only -------> proceed
  |
  v
openspec-review (existing stage)
```

## Design Decisions

### D1: Parallel dispatch via concurrent.futures

**Decision**: Use `concurrent.futures.ThreadPoolExecutor` to dispatch all three review agents concurrently, then collect results with `as_completed` or `executor.map`.

**Rationale**: Each agent is a subprocess (`subprocess.run`), so threads are appropriate (GIL is released during subprocess wait). The `concurrent.futures` module is stdlib, requires no new dependencies, and is the simplest way to run 3 independent subprocesses in parallel.

**Alternatives considered**:
- `asyncio.create_subprocess_exec`: Would require making the pipeline async. The pipeline is currently synchronous throughout. Converting just for this stage adds complexity for no benefit.
- Sequential dispatch: Would triple the wall-clock time for reviews. Reviews are independent, so parallel execution is the obvious choice.

### D2: New module `review_agents.py`

**Decision**: Create `src/action_harness/review_agents.py` containing: agent prompt builders, single-agent dispatch function, parallel dispatch orchestrator, output parser, triage function, and fix-feedback formatter.

**Rationale**: Review agents are a distinct concern from the existing `worker.py` (code implementation) and `openspec_reviewer.py` (spec validation). A dedicated module keeps responsibilities clear. The module follows the same pattern as `openspec_reviewer.py`: build prompt, dispatch CLI, parse output.

**Alternatives considered**:
- Adding to `worker.py`: Worker dispatch is specifically for implementation agents. Review agents have different prompts, different output schemas, and don't modify files. Mixing them would conflate two responsibilities.
- One module per agent type: Over-abstraction. All three agents share the same dispatch/parse pattern with only prompt differences.

### D3: Agents read PR diff, not worktree files

**Decision**: Review agents run with `cwd` set to the worktree (for `gh` CLI context) but their prompts instruct them to use `gh pr diff {number}` for the changes and to read files for context. They do NOT modify files.

**Rationale**: The PR is the artifact being reviewed. Using `gh pr diff` ensures agents review exactly what will be merged. Running in the worktree gives them access to read the full codebase for context via standard file tools. The `--permission-mode` is not `bypassPermissions` since review agents should not need to write files.

**Risk**: An agent might attempt to modify files despite instructions. Mitigation: use a restrictive permission mode (e.g., `default` with only read tools allowed). If a review agent modifies files, the worktree state check before OpenSpec review will detect unexpected changes.

### D4: Structured JSON output with fallback parsing

**Decision**: Each agent's system prompt instructs it to produce a JSON block with `{"findings": [...], "summary": "..."}`. The parser uses the same `_extract_json_block` pattern from `openspec_reviewer.py` to extract JSON from mixed prose/JSON output.

**Rationale**: Claude Code's `--output-format json` wraps the agent's output in a `{"result": "..."}` envelope. The agent's own output is a string that may contain prose before/after the JSON block. The existing `_extract_json_block` function handles this pattern reliably.

**Alternatives considered**:
- Requiring agents to output ONLY JSON: Agents naturally produce explanatory prose. Fighting this adds fragility. The existing JSON extraction pattern is proven.
- Custom output format (e.g., markdown tables): Harder to parse deterministically. JSON is the right format for machine consumption.

### D5: Single fix-retry with no re-review

**Decision**: If high/critical findings trigger a fix retry, the pipeline re-dispatches the code worker with findings as feedback, re-runs eval, and pushes to the PR branch. It does NOT re-run review agents after the fix.

**Rationale**: Re-running review agents after a fix creates a potential infinite loop (fix introduces new findings, new fix introduces new findings, etc.). A single retry captures the most value: the obvious bugs get fixed. If the fix introduces new bugs, those will be caught by human review or the next pipeline run. This matches the project principle: "corrections are cheap; waiting is expensive."

**Alternatives considered**:
- Re-review after fix: Risk of infinite loop. Requires a more complex termination condition (e.g., declining finding count). Over-engineered for the first version.
- No fix retry at all: Misses the opportunity to fix obvious bugs before human review. The whole point of review agents is to reduce human review burden.

### D6: Triage is deterministic, no LLM

**Decision**: Triage is a simple severity check: if any finding has severity "critical" or "high", trigger a fix retry. No LLM call is used for triage.

**Rationale**: This follows the core design rule: "Zero LLM calls in the orchestration layer." The agents produce severity ratings; the pipeline acts on them mechanically. This is testable without mocking LLMs.

### D7: ReviewResult as a new stage type

**Decision**: Add `ReviewResult` and `ReviewFinding` models to `models.py`. `ReviewResult` has `stage: Literal["review"]` and is added to `StageResultUnion`. Each agent dispatch produces one `ReviewResult`, so three appear in the manifest.

**Rationale**: Follows the existing pattern where each pipeline stage has a dedicated result model (`WorkerResult`, `EvalResult`, `PrResult`, `OpenSpecReviewResult`). Using a single `stage` literal "review" with an `agent_name` field distinguishes the three agents while keeping the discriminated union simple.

**Risk**: Three `ReviewResult` entries with the same `stage` discriminator value. Pydantic's discriminated union uses the `stage` field to determine the type, not the `agent_name`. This is fine because the discriminator just needs to map "review" -> `ReviewResult` class; the `agent_name` differentiates instances, not types.

### D8: Fix feedback format

**Decision**: When review findings trigger a fix retry, format the findings as structured markdown feedback similar to `evaluator.format_feedback`. Include the finding title, file, line, severity, description, and agent name. Instruct the worker to address high/critical findings and commit fixes.

**Rationale**: The worker already accepts a `feedback` string parameter. Review feedback follows the same pattern as eval feedback: structured information about what's wrong and what to fix.

### D9: PR comment for review summary

**Decision**: Post a single PR comment via `gh pr comment` summarizing all review findings, grouped by agent. This is separate from the PR body (which is created before reviews run).

**Rationale**: The PR body is created during the PR stage, before review agents run. Updating the PR body would require a separate `gh pr edit` call and would clobber the existing body structure. A comment is additive and preserves the timeline of events.

### D10: Permission mode for review agents

**Decision**: Review agents are dispatched with `--permission-mode bypassPermissions`, consistent with the code worker dispatch pattern.

**Rationale**: The harness runs headless (`-p` mode). Any permission mode that prompts for approval (including `default`) will hang the subprocess indefinitely since there is no stdin to respond. The system prompt instructs agents not to modify files — this is defense-in-depth, not the only safeguard.

## Integration Points

### Pipeline modification (`pipeline.py`)

The `_run_pipeline_inner` function gains a new stage between PR creation (Stage 4) and OpenSpec review (Stage 5):

```
Stage 4: Create PR (existing)
Stage 5: Review agents (NEW) — dispatch_review_agents() -> triage -> optional fix
Stage 6: OpenSpec review (existing, renumbered)
```

The fix retry within Stage 5 re-uses the existing `dispatch_worker` and `run_eval` functions from the worker/eval stages.

### Model updates (`models.py`)

```python
class ReviewFinding(BaseModel):
    title: str
    file: str
    line: int | None = None
    severity: Literal["critical", "high", "medium", "low"]
    description: str
    agent: str

class ReviewResult(StageResult):
    stage: Literal["review"] = "review"
    agent_name: str
    findings: list[ReviewFinding] = []
    cost_usd: float | None = None
```

`StageResultUnion` updated to include `ReviewResult`.

### Cost tracking

`ReviewResult.cost_usd` is parsed from Claude CLI's JSON output, same as `WorkerResult`. The `_build_manifest` function in `pipeline.py` needs updating to sum costs from `ReviewResult` entries in addition to `WorkerResult` entries.
