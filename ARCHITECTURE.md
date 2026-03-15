# Architecture

## System overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Human Operator                           │
│                   (intent, judgment, taste)                      │
└──────────────────────────┬──────────────────────────────────────┘
                           │ action-harness run
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
├── cli.py              CLI entry point (typer). Commands: run, clean
├── pipeline.py         Main orchestration — wires all stages together
├── models.py           Pydantic result types and run manifest
├── event_log.py        Structured JSON-lines event logging
│
├── worker.py           Dispatches Claude Code CLI, tracks cost/session
├── evaluator.py        Runs eval commands as subprocesses, formats feedback
├── profiler.py         Detects repo ecosystem and eval commands
│
├── worktree.py         Creates/manages isolated git worktrees
├── repo.py             Clones repos from URLs/paths, auth detection
│
├── pr.py               Creates PRs via gh with structured body
├── review_agents.py    Parallel review agents (bug, test, quality)
├── openspec_reviewer.py  Spec validation, semantic review, archival
│
├── protection.py       Protected path detection and PR flagging
└── parsing.py          JSON extraction from LLM output
```

## Pipeline control flow

```
action-harness run --change <name> --repo <path>
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
│     │  DISPATCH 3 AGENTS IN PARALLEL                      │
│     │  ├─ bug-hunter     (memory, races, logic, security) │
│     │  ├─ test-reviewer  (coverage, correctness, gaps)    │
│     │  └─ quality-reviewer (patterns, conventions, API)   │
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
└─ 8. MANIFEST
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
