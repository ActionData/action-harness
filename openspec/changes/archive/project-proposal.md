# Engineering Harness — Project Proposal

## Problem

Building AI-powered development infrastructure requires two fundamentally different execution modes that no single tool handles well:

1. **Interactive lead** — a conversational tech/product lead that explores codebases, writes specs, makes judgment calls, and delegates work. Needs prompt caching, planning, parallel tool calls, MCP access. This is Claude Code.

2. **Autonomous pipeline** — headless orchestration that takes tasks, spins up workers in isolation, runs eval, manages retries, opens PRs, gets reviews, iterates, and merges. No human in the loop until escalation.

Current approaches fall short:

- **nullharness** — correct pipeline design (multi-phase, smart dispatch, worktree isolation, repo onboarding) but coupled to nullclaw's agent loop, which currently lacks token caching, planning, and parallel tool calls. Adding these to the Zig agent loop is possible but would take significant effort, and Claude Code already provides all of them today.
- **ai-harness** — right idea using Claude Code as the agent runtime, but only implements a single eval→retry loop. No pipeline phases, no review agents, no channels, no always-on operation.
- **Claude Code alone** — excellent interactive agent, but no structured pipeline, no automated eval/retry, no multi-agent review, no always-on channel intake.

## Vision

An always-on engineering system that acts as your engineering manager and engineering team. You interact with it conversationally (via Claude Code) to explore, plan, and write specs. When implementation is needed, the harness takes over: it plans the work, dispatches coding agents in isolated worktrees, runs real eval (build, test, lint), feeds back failures, manages retries, opens PRs, dispatches specialized review agents, iterates on review feedback, and merges — escalating to a human only when judgment is required.

The system watches external channels (GitHub issues, Linear tickets, webhooks) for triggers and can autonomously pick up work, create OpenSpec proposals, and execute them through the pipeline.

```
You (human)
  ↕
Claude Code (interactive lead — you already use this today)
  ↕
Harness (autonomous pipeline — this is what we're building)
  ↕
External systems (GitHub, Linear, CI, production)
```

## Design Principles

### Claude Code as the agent runtime

Every worker invocation uses Claude Code programmatically. Claude Code already has prompt caching, planning, parallel tool calls, MCP servers, file I/O, shell access, and web search. Rather than rebuilding these capabilities in a custom agent loop, the harness uses Claude Code directly and gets all current and future capabilities for free.

The harness's job is orchestration, not agent execution. It decides *what* to run, *when*, and *in what order*. Claude Code decides *how*.

**Open question: CLI vs SDK.** Two options for invoking Claude Code programmatically:

1. **CLI wrapping** (`claude -p "prompt" --output-format json`): Battle-tested, works today. Supports `--allowedTools`, `--system-prompt`, `--max-turns`, `--max-budget-usd`, `--output-format json`. Each worker is a subprocess. Simple, reliable, no library dependency.

2. **Agent SDK** (`claude-agent-sdk`): Native Python async, structured message objects, hooks and subagent support. More ergonomic for a Python harness, but newer and needs validation that it provides the same capabilities as the CLI (tool access, MCP, CLAUDE.md loading).

Decision deferred to Phase 0 — try both, pick the one that works better for headless worker dispatch.

### Evaluation is external, not self-reported

The agent doesn't grade its own homework. The harness runs real eval commands (build, test, lint, type check) as subprocesses and checks exit codes. The agent's self-assessment (summary, confidence) is captured for context but doesn't determine pass/fail.

This is what makes the retry loop trustworthy. A failing test is ground truth. An agent saying "I think it works" is not.

### The supervisor is a pure state machine

Zero LLM calls in orchestration logic. The supervisor reads events, transitions state, and dispatches workers. All decisions (which phase next, whether to retry, whether to skip review) are deterministic and based on observable state — repo profile, eval results, git status, task metadata.

This makes the pipeline testable without mocking LLMs. You can write unit tests for every dispatch decision.

### Python for the orchestration layer

The hard work happens inside Claude Code. The harness is glue code — subprocess dispatch, state management, event routing, git operations. Python gives you rapid iteration, pydantic for models, asyncio for concurrency, and a massive ecosystem for integrations (GitHub API, Linear SDK, webhooks).

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                   Intake Layer                        │
│                                                      │
│  CLI ──────┐                                         │
│  GitHub ───┤                                         │
│  Linear ───┼──→ Event Router ──→ Task Queue          │
│  Webhook ──┤                                         │
│  Cron ─────┘                                         │
└──────────────────────┬───────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────────┐
│                  Supervisor                           │
│             (deterministic state machine)             │
│                                                      │
│  Task ──→ Onboard Repo                               │
│           ──→ Create Worktree                         │
│           ──→ Plan (optional, for complex goals)      │
│           ──→ Code (Claude Code worker)               │
│           ──→ Eval (subprocess: build, test, lint)    │
│           ──→ Feedback → Retry (if eval fails)        │
│           ──→ Review (Claude Code reviewer agent)     │
│           ──→ Feedback → Iterate (if review fails)    │
│           ──→ PR (open, request review, merge)        │
│                                                      │
│  Smart dispatch:                                      │
│  - Skip test if no test infra detected               │
│  - Skip review for trivial changes                   │
│  - Parallel workers for independent sub-tasks        │
│  - Budget/guardrail enforcement at every phase       │
└──────────────────────┬───────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────────┐
│                 PR Manager                            │
│                                                      │
│  Open PR with structured description                 │
│  Dispatch review agents (bug hunter, quality, tests) │
│  Collect findings, triage by severity                │
│  Dispatch fix agent for high-severity findings       │
│  Push updates, re-request review                     │
│  Merge when clean                                    │
└──────────────────────────────────────────────────────┘
```

## Core Components

### Worker — Claude Code wrapper

Thin programmatic wrapper around Claude Code. Configurable per role:

| Role | System prompt focus | Max turns | Eval strategy |
|------|-------------------|-----------|---------------|
| Coder | Implement the task, commit changes | 15–20 | Build + test + lint |
| Test writer | Add/fix tests for the diff | 10 | Test suite passes |
| Reviewer | Review git diff, report findings | 5 | Structured findings output |
| Planner | Decompose goal into ordered tasks | 5 | Valid task list output |
| Fixer | Address specific review findings | 10 | Build + test + lint |

Each worker runs in its own worktree. Workers are stateless — fresh Claude Code invocation per dispatch, no memory bleed between tasks.

**CLI mode:**
```bash
claude -p "$prompt" \
  --output-format json \
  --allowedTools "Read,Edit,Bash,Write" \
  --system-prompt "$role_prompt" \
  --max-turns 15 \
  --working-directory /tmp/worktrees/task-123
```

**SDK mode (if validated):**
```python
async for message in query(
    prompt=prompt,
    options=ClaudeAgentOptions(
        cwd=worktree_path,
        allowed_tools=["Read", "Edit", "Bash"],
        system_prompt=role_prompt,
        max_turns=15,
    ),
):
    ...
```

### Evaluator — subprocess-based

Runs eval commands defined per repo (detected during onboarding or specified in config):

```yaml
eval_commands:
  - name: build
    command: ["uv", "run", "python", "-m", "py_compile", "src/main.py"]
  - name: test
    command: ["uv", "run", "pytest", "-v"]
  - name: lint
    command: ["ruff", "check", "."]
  - name: typecheck
    command: ["uv", "run", "mypy", "src/"]
```

Exit code 0 = pass. Everything else = fail with captured stdout/stderr fed back to the agent.

### Repo Profile — auto-detected context

On first contact with a repo, the harness scans for:

- Build system (cargo, go, npm, uv/pip, make)
- Test infrastructure (test dirs, test config, pytest, jest, go test)
- Lint/format tools (ruff, eslint, rustfmt, prettier)
- Project instructions (CLAUDE.md, README.md)
- Language and framework

This profile is injected into every worker prompt and used for smart dispatch decisions (skip test-runner if no tests exist, etc.).

### State Store — persistent task state

Each task gets a JSON state file tracking:

- Current phase, retry count, timestamps
- Per-phase results (eval output, review findings)
- Worker invocation history
- PR URL and review status

State survives process restarts. The harness can resume in-progress work after a crash.

### Guardrails

- Max iterations per phase (don't let a stuck coder loop forever)
- Max files changed (catch runaway agents)
- Allowed path patterns (restrict where agents can write)
- Cost budget per task (`--max-budget-usd` flag)
- Wall-clock timeout per worker invocation

## What This Is NOT

- **Not a custom agent framework.** Claude Code is the agent runtime. The harness is orchestration only.
- **Not an IDE.** The interactive lead experience is Claude Code itself. The harness is the headless pipeline that Claude Code triggers.
- **Not a CI/CD system.** It doesn't replace GitHub Actions. It uses CI as a signal (detect failures, auto-fix) and as a gate (CI must pass before merge).
- **Not multi-tenant.** Single operator, multiple repos. Not a SaaS platform.

## Phased Delivery

### Phase 0: Core Pipeline
- CLI: `harness run "task description" --repo ./path`
- Single-phase: Claude Code coder → subprocess eval → feedback → retry
- Worktree isolation
- Repo onboarding (auto-detect build/test/lint)
- JSON state persistence
- Guardrails
- Validate CLI vs SDK for Claude Code invocation

### Phase 1: Multi-Phase Pipeline
- Coder → eval → review pipeline
- Smart dispatch (skip phases based on repo profile and change type)
- PR manager (open PR, push updates)
- Specialized review agents (bug hunter, quality, test coverage)
- Review finding triage and auto-fix

### Phase 2: Planning & OpenSpec
- Planner agent for complex goal decomposition
- OpenSpec-aware task creation (read proposals, generate tasks)
- Multi-task execution (dependency ordering, parallel where possible)

### Phase 3: Always-On
- Server mode with event loop
- GitHub webhook intake (issues, PR comments, CI failures)
- Linear integration
- Cron-based monitoring (watch for new issues, stale PRs)
- Escalation protocol (auto-handle → notify lead → escalate to human)

## Project Bootstrapping

### Carry forward from nullharness

The following development practices and tooling are portable and should be adopted in the new repo:

**CLAUDE.md conventions:**
- Vision section at the top — what the project is and isn't
- Build & test commands — exact commands for build, test, format, lint
- Architecture section with module layout and dependency direction
- Code quality rules — no silent failures, match existing patterns, never propagate bad patterns
- OpenSpec workflow — proposal-first development is mandatory, not optional

**OpenSpec skills and commands** (`.claude/` directory):
- `opsx:propose` — create a new change with all artifacts
- `opsx:apply` — implement tasks from an OpenSpec change
- `opsx:archive` — archive completed changes
- `opsx:explore` — think through ideas before committing to a change
- Ship skill — create PR, run parallel review agents, triage findings, push fixes

**Code quality rules (portable across languages):**
- Never propagate bad patterns. If you find one, fix it or track it — don't copy it.
- Proposal-first development. Every non-trivial change starts with an OpenSpec proposal.
- Self-validation is required. Every proposal must include validation steps runnable without human involvement.
- The implementing agent must be able to build, test, and validate its own work.
- A separate agent should perform review and testing — don't let the same agent mark its own homework.

### New repo structure

```
harness/
├── pyproject.toml
├── CLAUDE.md
├── README.md
├── .claude/
│   ├── commands/opsx/     # OpenSpec slash commands
│   └── skills/            # OpenSpec + ship skills
├── openspec/
│   ├── ROADMAP.md
│   └── changes/
├── src/harness/
│   ├── __init__.py
│   ├── cli.py             # CLI entrypoint
│   ├── supervisor.py      # State machine
│   ├── worker.py          # Claude Code wrapper
│   ├── evaluator.py       # Subprocess eval
│   ├── onboard.py         # Repo profile detection
│   ├── worktree.py        # Git worktree management
│   ├── state.py           # Pydantic models + persistence
│   ├── guardrails.py      # Budget/safety limits
│   ├── prompt.py          # Role-specific prompt builder
│   └── feedback.py        # Eval failure → structured feedback
└── tests/
```

