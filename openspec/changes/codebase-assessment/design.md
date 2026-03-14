## Context

The harness currently has a `profiler.py` that detects ecosystem markers, parses CLAUDE.md for build commands, and produces a `RepoProfile` with eval commands. This runs once per pipeline execution and answers "what can I run?" but not "how reliable is this repo for autonomous work?"

The assessment extends profiling from presence-detection to quality-assessment. It needs to evaluate CI workflows, test effectiveness, documentation quality, and tooling maturity — some of which can be done mechanically, some of which requires an agent reading the actual code.

## Goals / Non-Goals

**Goals:**
- `harness assess` CLI command with three progressive modes (base, `--deep`, `--propose`)
- Mechanical scan that goes beyond file presence to parse CI workflows, check configs, and assess structural quality
- Agent-based quality assessment for dimensions that require judgment (test quality, documentation clarity)
- Structured scoring model with per-category scores, findings, and gap identification
- Automated OpenSpec proposal generation for identified gaps via spec-writer agents
- JSON output for persistence and comparison over time

**Non-Goals:**
- Running the full test suite as part of assessment (that's eval, not assessment)
- Continuous monitoring or scheduled reassessment (future: `always-on`)
- Modifying the target repo during assessment (assessment is read-only)
- Scoring thresholds that block pipeline execution (assessment is advisory)
- Custom scoring weights or category configuration (keep it simple, add later if needed)

## Decisions

### 1. Three-mode CLI with additive flags

```
harness assess --repo ./path                  # mechanical scan only
harness assess --repo ./path --deep           # + agent quality assessment
harness assess --repo ./path --deep --propose # + generate OpenSpec proposals
```

`--propose` implies `--deep`. Each mode builds on the previous. The base scan is free and fast. `--deep` costs one agent dispatch. `--propose` costs N additional spec-writer dispatches (one per gap).

**Alternative considered:** Single mode that always does everything. Rejected — the operator should control cost and speed. The base scan is useful on its own for quick checks.

### 2. Six scoring categories

| Category | What it measures | Mechanical signals | Agent assessment |
|----------|-----------------|-------------------|-----------------|
| Context | Can the agent understand the codebase? | CLAUDE.md, README, HARNESS.md, AGENTS.md presence; type annotation coverage | Documentation quality, architecture clarity |
| Testability | Can the agent verify its work? | Test framework, test file count, test function count, coverage config | Test quality (meaningful assertions? error paths? integration tests?) |
| CI Guardrails | Will CI catch what the agent misses? | Workflow files, trigger events, step parsing, branch protection (GitHub API) | Whether CI steps are comprehensive vs superficial |
| Observability | Can the agent see runtime behavior? | Structured logging libs, health endpoints, metrics/tracing deps | Logging quality, whether logs are actionable |
| Tooling | What tools can the agent use? | Package manager, lockfiles, MCP configs, Claude skills, Docker/compose | Whether available tools cover common operations |
| Isolation | Can the agent work safely? | Git worktree support, .env.example, no committed secrets, lockfiles | Whether builds are reproducible |

Each category scores 0-100. Overall score is the average. Categories have mechanical signals (always computed) and optional agent assessments (only with `--deep`).

### 3. Mechanical scan extends profiler.py

The existing `profile_repo()` already detects ecosystem and eval commands. The mechanical scan adds:

- **CI workflow parsing**: parse `.github/workflows/*.yml` to extract trigger events, job steps, and match against known tool patterns (pytest, ruff, eslint, etc.)
- **Branch protection**: `gh api repos/{owner}/{repo}/branches/{branch}/protection` to check required status checks and reviewers
- **Test structure analysis**: count test files, test functions (grep for `def test_` / `it(` / `#[test]`), check for coverage config
- **Dependency lockfiles**: check for `uv.lock`, `package-lock.json`, `Cargo.lock`, `go.sum`
- **File markers for each category**: MCP configs (`.claude/mcp*.json`), Docker files, `.env.example`, type annotation sampling

These are all deterministic file/config parsing — no LLM needed. The scan produces a `MechanicalSignals` model (structured JSON) that feeds into scoring.

### 4. Assessment agent is a read-only Claude Code dispatch

The assessment agent is a Claude Code worker with:
- System prompt: assessment role with scoring rubric
- Input: mechanical signals JSON + instructions per category
- Allowed tools: Read, Glob, Grep, Bash (for `gh api` calls) — no Edit, no Write
- Output format: structured JSON with adjusted scores, rationale, and findings
- No commits expected — the worker success check is JSON output, not commit count

This follows the existing worker dispatch pattern but with different success criteria. A new `dispatch_readonly_worker()` function in `worker.py` handles this — separate from `dispatch_worker()` to avoid changing the coder worker's signature. It passes `--allowedTools "Read,Glob,Grep,Bash"` to the Claude CLI, does NOT call `count_commits_ahead`, and returns parsed JSON output or None on failure.

**Alternative considered:** Adding a `mode` parameter to `dispatch_worker()`. Rejected — the two functions have fundamentally different success criteria (commits vs JSON output) and different return types. A new function is cleaner than branching logic inside the existing one.

### 5. Spec-writer agents dispatch in parallel for gap proposals

For each gap identified (by mechanical scan or agent assessment), the harness dispatches a spec-writer agent to create an OpenSpec proposal. These are independent and parallelizable.

Each spec-writer agent gets:
- The gap finding (severity, description, category)
- The repo context (ecosystem, existing tools, CLAUDE.md)
- Instructions to create a focused OpenSpec change with proposal.md

The harness orchestrates this deterministically: read assessment JSON → extract gaps → dispatch N spec-writers → collect results.

### 6. Assessment report model

```python
class Gap(BaseModel):
    severity: Literal["high", "medium", "low"]
    finding: str
    category: str
    proposal_name: str | None  # kebab-case, used for --propose

# Typed mechanical signals per category (examples):
class CIMechanicalSignals(BaseModel):
    ci_exists: bool
    triggers_on_pr: bool
    runs_tests: bool
    runs_lint: bool
    runs_typecheck: bool
    runs_format_check: bool
    branch_protection: bool | None  # None = unable to assess

class TestabilityMechanicalSignals(BaseModel):
    test_framework_configured: bool
    test_files: int
    test_functions: int
    coverage_configured: bool

# ... similar typed models for context, tooling, observability, isolation

class CategoryScore(BaseModel):
    score: int  # 0-100
    mechanical_signals: (CIMechanicalSignals | TestabilityMechanicalSignals
                         | ContextMechanicalSignals | ToolingMechanicalSignals
                         | ObservabilityMechanicalSignals | IsolationMechanicalSignals)
    agent_assessment: str | None  # only with --deep
    gaps: list[Gap]

class AssessmentReport(BaseModel):
    overall_score: int
    categories: dict[str, CategoryScore]
    proposals: list[Gap]  # gaps with severity >= threshold
    repo_path: str
    timestamp: str
    mode: Literal["base", "deep", "propose"]
```

The report is printed to terminal (formatted) and optionally saved as JSON for tracking over time.

## Risks / Trade-offs

- [Cost] `--deep` requires one agent dispatch, `--propose` adds N more → Mitigation: modes are opt-in. Base scan is free. Document expected costs.
- [Scoring subjectivity] Agent quality judgments will vary between runs → Mitigation: mechanical signals provide the stable baseline. Agent assessment adjusts but doesn't override. Document that scores are approximate.
- [CI parsing brittleness] GitHub Actions YAML has many forms (composite actions, reusable workflows, matrix strategies) → Mitigation: parse conservatively. Unknown patterns score as "unable to assess" rather than penalizing.
- [GitHub API rate limits] Branch protection checks require authenticated API calls → Mitigation: make GitHub API checks optional. Degrade gracefully if `gh` is not authenticated or rate-limited.
- [Proposal quality] Auto-generated proposals might be too generic → Mitigation: spec-writer agents get repo-specific context (ecosystem, existing tools, CLAUDE.md). Review is expected before implementation.
