# CLAUDE.md — action-harness

## Vision

Action-harness is an autonomous engineering pipeline that orchestrates Claude Code workers through the full development lifecycle — from task intake to merge. It is a **deterministic Python state machine** that decides *what* to run, *when*, and *in what order*. Claude Code decides *how*.

The system acts as your engineering manager and engineering team. You interact conversationally via Claude Code to explore, plan, and write specs. When implementation is needed, the harness takes over: dispatching coding agents in isolated worktrees, running real eval (build, test, lint), feeding back failures, managing retries, opening PRs, dispatching specialized review agents, iterating on feedback, and merging — escalating to a human only when judgment is required.

```
You (human)
  ↕
Claude Code (interactive lead — you already use this)
  ↕
action-harness (autonomous pipeline — this is what we're building)
  ↕
External systems (GitHub, Linear, CI, production)
```

### What this is NOT

- **Not a custom agent framework.** No custom LLM client, no custom tool system, no custom agent loop. Claude Code is the agent.
- **Not an IDE.** The interactive lead experience is Claude Code itself. The harness is the headless pipeline.
- **Not a CI/CD system.** It uses CI as a signal and gate, not a replacement for GitHub Actions.
- **Not multi-tenant.** Single operator, multiple repos.

## Build & Test

```bash
uv sync                          # install dependencies
uv run pytest -v                  # run all tests
uv run ruff check .               # lint
uv run ruff format --check .      # check formatting
uv run mypy src/                  # type check
```

Requires Python 3.13+ and `uv`.

## Architecture

### Module layout

```
src/action_harness/
├── __init__.py
├── cli.py             # CLI entrypoint (typer)
├── supervisor.py      # Deterministic state machine
├── worker.py          # Claude Code wrapper (CLI or SDK)
├── evaluator.py       # Subprocess eval runner
├── onboard.py         # Repo profile detection
├── worktree.py        # Git worktree management
├── state.py           # Pydantic models + JSON persistence
├── guardrails.py      # Budget/safety limits
├── prompt.py          # Role-specific prompt builder
└── feedback.py        # Eval failure → structured feedback
```

### Key design rules

- **Supervisor is deterministic.** Zero LLM calls in orchestration logic. It reads events, transitions state, and dispatches workers. All decisions are based on observable state — repo profile, eval results, git status, task metadata. Testable without mocking LLMs.
- **External evaluation.** The agent doesn't grade its own homework. The harness runs eval commands as subprocesses and checks exit codes. Agent self-assessment is captured for context but doesn't determine pass/fail.
- **Worktree isolation.** Every task gets its own git worktree. Workers operate in isolation, not the main repo checkout.
- **Smart dispatch.** Skip phases based on repo context. No test infra → skip tests. No code changes → skip review. Don't waste API calls on agents with nothing to do.
- **Workers are stateless.** Each dispatch is a fresh Claude Code invocation. No memory bleed between tasks.
- **Claude Code is the agent runtime.** Every worker invocation uses Claude Code programmatically. The harness gets prompt caching, planning, parallel tool calls, MCP servers, and everything Anthropic ships in the future — for free.

## Code quality rules

- **Never propagate bad patterns.** "It already exists elsewhere" is not justification. Fix it or track it as tech debt — don't copy it.
- **No silent failures.** Log errors that affect task flow. The supervisor should log worker output on every phase transition.
- **Proposal-first development.** Every non-trivial change starts with an OpenSpec proposal. The proposal, design, and task artifacts must exist before implementation begins.
- **Self-validation is required.** Every proposal must include validation steps runnable without human involvement.
- **Agent independence.** The implementing agent must be able to build, test, and validate its own work. A separate agent should perform review — don't let the same agent mark its own homework.

## OpenSpec workflow

All features and fixes follow the OpenSpec lifecycle. This is mandatory, not optional.

```
propose → [resolve prerequisites] → implement → self-validate → archive
```

See `openspec/ROADMAP.md` for the current change sequence and dependencies.
