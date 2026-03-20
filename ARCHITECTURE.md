# Architecture

## System overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Human Operator                           │
│                   (intent, judgment, taste)                      │
└──────────────────────────┬──────────────────────────────────────┘
                           │ ah run
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                     CLI (cli.py)                                │
│  Parses flags, validates prerequisites (claude, gh),            │
│  profiles repo, invokes pipeline                                │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Pipeline (pipeline.py)                          │
│  Deterministic orchestration — zero LLM calls.                  │
│  Reads state, runs subprocesses, checks exit codes.             │
│                                                                 │
│  ┌───────────┐ ┌──────────┐ ┌───────────┐ ┌──────────────────┐ │
│  │ Worktree  │ │ Worker   │ │ Evaluator │ │ PR / Review      │ │
│  │ Manager   │ │ Dispatch │ │           │ │ Agents           │ │
│  └───────────┘ └──────────┘ └───────────┘ └──────────────────┘ │
└──────────────────────────┬──────────────────────────────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  Git / FS    │  │ Claude Code  │  │   GitHub      │
│  Worktrees,  │  │ CLI          │  │   gh CLI      │
│  branches    │  │ (the agent)  │  │   PRs, labels │
└──────────────┘  └──────────────┘  └──────────────┘
```

## Module map

```
src/action_harness/
│
│  Core pipeline
├── cli.py                CLI entry point (typer). Commands: run, clean, assess, dashboard, etc.
├── pipeline.py           Main orchestration — wires all stages together
├── models.py             Pydantic result types and run manifest
├── event_log.py          Structured JSON-lines event logging
├── checkpoint.py         Pipeline checkpoints for resume across process failures
│
│  Worker and evaluation
├── worker.py             Dispatches Claude Code CLI, tracks cost/session
├── evaluator.py          Runs eval commands as subprocesses, formats feedback
├── profiler.py           Detects repo ecosystem and eval commands
├── progress.py           Progress file writing for retry context between dispatches
│
│  Git and repo management
├── worktree.py           Creates/manages isolated git worktrees
├── repo.py               Clones repos from URLs/paths, auth detection
├── tags.py               Git tag management for rollback points and shipped markers
│
│  PR, review, and merge
├── pr.py                 Creates PRs via gh with structured body
├── review_agents.py      Parallel review agents (bug, test, quality, spec-compliance)
├── openspec_reviewer.py  Spec validation, semantic review, archival
├── merge.py              Auto-merge logic: gate checks, CI wait, PR merge
├── protection.py         Protected path detection and PR flagging
├── branch_protection.py  GitHub API branch protection checks
│
│  Assessment and reporting
├── assess_agent.py       Assessment agent dispatch — read-only Claude Code worker
├── assessment.py         Assessment models for codebase readiness scoring
├── scoring.py            Scoring logic for codebase assessment
├── scanner.py            Mechanical scanners for codebase assessment
├── formatter.py          Terminal output formatting for assessment reports
├── gap_proposals.py      Gap proposal generation — OpenSpec changes from assessment
├── reporting.py          Run manifest aggregation and failure reporting
│
│  Intake and observability
├── issue_intake.py       GitHub issue intake: read issues, detect OpenSpec references
├── dashboard.py          Dashboard data layer — workspace and repo visibility
├── progress_feed.py      Live progress feed — tails event logs for display
├── ci_parser.py          CI workflow parsing — extract signals from GitHub Actions
│
│  Agent definitions and knowledge
├── agents.py             Agent definition file loading: frontmatter, paths, prompts
├── catalog/              Agent knowledge catalog
│   ├── loader.py         Loading catalog entries with per-repo overrides
│   ├── models.py         Catalog data structures
│   ├── renderer.py       Rendering findings with context
│   ├── frequency.py      Finding frequency tracking per repo
│   └── entries/          YAML entries with ecosystem filtering
│
│  Utilities
├── parsing.py            JSON extraction from LLM output
└── slugify.py            Prompt-to-slug conversion for branch naming
```

## Pipeline control flow

```
ah run --change <name> --repo <path>
│
├─ 0. CHECKPOINT CHECK (if --resume latest)
│     Load last checkpoint from .action-harness/checkpoints/
│     Validate branch HEAD matches, resume from last completed stage
│
├─ 1. VALIDATE
│     Assert claude and gh CLIs exist
│     Profile repo → detect ecosystem, eval commands
│     Dry-run exits here with plan summary
│
├─ 2. WORKTREE
│     Clean prior branch/worktree if exists
│     git worktree add -b harness/<name> <path> <base>
│     │
│     ├─ Local repo → temp dir (/tmp/action-harness-*)
│     └─ Managed repo → persistent dir (<harness-home>/workspaces/<repo>/<change>/)
│
├─ 3. DISPATCH + EVAL LOOP (up to max_retries)
│     │
│     │  ┌──────────────────────────────────────────────┐
│     │  │                                              │
│     │  ▼                                              │
│     │  DISPATCH WORKER                                │
│     │  claude -p <prompt> --output-format json        │
│     │  │                                              │
│     │  ├─ First attempt: fresh dispatch               │
│     │  └─ Retry: resume session if context < 60%,     │
│     │           otherwise fresh dispatch with feedback │
│     │  │                                              │
│     │  ▼                                              │
│     │  RUN EVAL                                       │
│     │  pytest → ruff → mypy → ...                     │
│     │  (first failure stops; structured feedback)      │
│     │  │                                              │
│     │  ├─ All pass → break, continue to PR            │
│     │  └─ Failure → retry ────────────────────────────┘
│     │
│     └─ Max retries exceeded → cleanup, abort
│
├─ 4. CREATE PR
│     git push -u origin harness/<name>
│     gh pr create --title "[harness] <name>" --body <manifest summary>
│     │
│     Body includes: proposal context, diff stats, commits,
│     worker cost/duration, eval results
│
├─ 5. PROTECTED PATHS CHECK
│     Load .harness/protected-paths.yml
│     Diff changed files against patterns
│     │
│     ├─ No matches → continue
│     └─ Matches → comment on PR, add "protected-paths" label
│
├─ 6. REVIEW AGENTS (up to 2 fix-retry rounds)
│     │
│     │  ┌──────────────────────────────────────────────────┐
│     │  │                                                  │
│     │  ▼                                                  │
│     │  DISPATCH 4 AGENTS IN PARALLEL                      │
│     │  ├─ bug-hunter     (memory, races, logic, security) │
│     │  ├─ test-reviewer  (coverage, correctness, gaps)    │
│     │  ├─ quality-reviewer (patterns, conventions, API)   │
│     │  └─ spec-compliance (task vs implementation match)   │
│     │  │                                                  │
│     │  ▼                                                  │
│     │  TRIAGE FINDINGS                                    │
│     │  │                                                  │
│     │  ├─ No critical/high → post comment, continue       │
│     │  └─ Critical/high found →                           │
│     │       Re-dispatch worker with review feedback       │
│     │       Re-run eval                                   │
│     │       Push fixes                                    │
│     │       Post update comment                           │
│     │       └─ Loop back for verification review ─────────┘
│     │
│     └─ Post final findings comment on PR
│
├─ 7. OPENSPEC REVIEW
│     Validate spec completion (tasks done?)
│     Semantic review of change artifacts
│     │
│     ├─ Approved → auto-archive change
│     ├─ Findings → abort with issues
│     └─ Needs human → add label, comment with human tasks
│
├─ 8. AUTO-MERGE (optional, --auto-merge flag)
│     Gate checks: no protected files, review clean, openspec approved
│     Optional --wait-for-ci: poll CI checks before merge
│     │
│     ├─ All gates pass → merge PR
│     └─ Gate failed → post blocked comment, skip merge
│
└─ 9. MANIFEST
      Write RunManifest to .action-harness/runs/<run_id>.json
      Close event log (.events.jsonl)
      Return success/failure
```

## Eval command discovery

The profiler finds eval commands in priority order:

1. **CLAUDE.md** — parses the `## Build & Test` section for commands in fenced code blocks
2. **Convention** — inspects `pyproject.toml`, `package.json`, `Cargo.toml` for tool config
3. **Fallback** — bootstrap defaults for the detected ecosystem

## Worktree lifecycle

```
create                  use                     cleanup
───────────────────     ──────────────────      ──────────────────
git worktree add   →    worker runs here   →    remove directory
-b harness/<name>       eval runs here          prune worktree
                        commits stay here       branch preserved
                                                (for inspection)
```

Workers never touch the main checkout. Each dispatch operates exclusively in its worktree.

## Data flow

```
                    ┌─────────────┐
                    │ RepoProfile │ ecosystem, eval commands
                    └──────┬──────┘
                           │
┌──────────────┐    ┌──────▼──────┐    ┌────────────┐
│WorktreeResult│───▶│WorkerResult │───▶│ EvalResult  │
│ path, branch │    │ commits,    │    │ pass/fail,  │
└──────────────┘    │ cost,       │    │ feedback    │
                    │ session_id  │    └──────┬──────┘
                    └─────────────┘           │
                                      ┌──────▼──────┐
                                      │  PrResult   │
                                      │  pr_url     │
                                      └──────┬──────┘
                                             │
                    ┌────────────────┐ ┌──────▼──────────────┐
                    │ ReviewResult[] │ │OpenSpecReviewResult  │
                    │ findings,     │ │ tasks, validation,   │
                    │ severity      │ │ archived             │
                    └───────┬───────┘ └──────────┬───────────┘
                            │                    │
                      ┌─────▼────────────────────▼─────┐
                      │          RunManifest            │
                      │  Aggregates all stage results   │
                      │  total cost, duration, outcome  │
                      └────────────────────────────────┘
```

## Key design decisions

- **Zero LLM calls in orchestration.** The pipeline is deterministic — subprocess calls, exit codes, git operations. Testable without mocking LLMs.
- **Claude Code is the agent runtime.** No custom LLM client. The harness dispatches `claude` CLI and benefits from upstream improvements.
- **External evaluation.** Agents don't grade their own work. Eval is subprocess exit codes.
- **Stateless workers.** Each dispatch is fresh. Context comes from the repo and the prompt. Session resume is an optimization, not a requirement.
- **Structured results.** Every stage returns a typed Pydantic model. The run manifest aggregates them all.

See [`PROJECT_VISION.md`](PROJECT_VISION.md) for core beliefs and success criteria.
