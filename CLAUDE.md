# CLAUDE.md — action-harness

## Vision

Action-harness is a self-hosting harness. It automates the task-to-merge workflow by orchestrating Claude Code workers: task intake, implementation in isolated worktrees, external evaluation, retry with structured feedback, and PR creation.

The organizing goal is self-hosting: build the minimum loop by hand, then the harness builds everything else — review agents, auto-merge, observability, repo profiling — as tasks on its own codebase.

See `PROJECT_VISION.md` for the full vision and core beliefs. See `openspec/ROADMAP.md` for the self-hosted backlog.

```
Human (intent, judgment, taste)
  ↕
Claude Code (interactive lead)
  ↕
action-harness (autonomous pipeline — self-hosting)
  ↕
Target repositories (starting with itself)
  ↕
External systems (GitHub, CI)
```

## Build & Test

```bash
uv sync                          # install dependencies
uv run pytest -v                  # run all tests
uv run ruff check .               # lint
uv run ruff format --check .      # check formatting
uv run mypy src/                  # type check
```

Requires Python 3.13+ and `uv`.

## Key design rules

- **External evaluation.** The agent doesn't grade its own homework. The harness runs eval commands as subprocesses and checks exit codes. Agent self-assessment is context, not the gate.
- **Deterministic orchestration.** Zero LLM calls in the orchestration layer. It reads state, runs subprocesses, checks exit codes, and dispatches workers. Testable without mocking LLMs.
- **Worktree isolation.** Every task gets its own git worktree. Workers never touch the main checkout.
- **Claude Code is the agent runtime.** No custom LLM client or agent loop. The harness dispatches Claude Code CLI and benefits from every upstream improvement.
- **Workers are stateless.** Each dispatch is a fresh Claude Code invocation. Context comes from the repo and the prompt.
- **Minimal abstraction.** Functions that call subprocess.run and parse JSON. No framework.
- **Agent-debuggable by default.** Every function that performs I/O (subprocess, git, file) logs to stderr and returns a structured result. No fire-and-forget. Pipeline stages are independently callable with explicit typed parameters. stderr is the diagnostic channel (progress, timing, outcomes); stdout is reserved for final output (exception: `--dry-run` prints the plan to stdout).

### Logging conventions

Use `typer.echo(..., err=True)` for stderr output. One line at stage entry (stage name + key inputs), one line at stage exit (stage name + outcome). Default is concise. `--verbose` adds subprocess command details, working directories, and output previews.

## CLI documentation

The CLI help text (`--help`) is the API documentation. When adding or changing commands, flags, or behavior, update the typer docstrings, option help strings, and epilog to match. No separate usage docs — keep the help output as the single source of truth.

## Code quality rules

- **Never propagate bad patterns.** Fix or track as tech debt — don't copy.
- **No silent failures.** Log errors that affect task flow.
- **Proposal-first development.** Every non-trivial change starts with an OpenSpec proposal.
- **Self-validation is required.** Every proposal includes validation steps.
- **Agent independence.** The implementing agent validates its own work. A separate agent reviews.

## OpenSpec workflow

All features follow the OpenSpec lifecycle:

```
propose → [resolve prerequisites] → implement → self-validate → archive
```

See `openspec/ROADMAP.md` for the current change sequence.
