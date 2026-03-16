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
- **No `Any` types.** Use specific types. If a value can be multiple types, use a union (`str | int | None`). `Any` is only acceptable for truly dynamic kwargs (e.g., `**metadata: Any` for JSON-serializable values). Never use `Any` to avoid thinking about the type.
- **Proposal-first development.** Every non-trivial change starts with an OpenSpec proposal.
- **Self-validation is required.** Every proposal includes validation steps.
- **Agent independence.** The implementing agent validates its own work. A separate agent reviews.

### Subprocess safety
- Every `subprocess.run()` call MUST include a `timeout=` parameter. Use 120s for CLI tools (`gh`, `git`), 600s for long-running operations.
- Catch `subprocess.TimeoutExpired` alongside `FileNotFoundError` and `OSError` in except clauses.

### Type safety
- Never use bare `assert x is not None` for type narrowing — assertions are stripped by `python -O`. Use explicit `if x is None: raise ValueError(...)` or restructure the conditional so mypy narrows naturally.
- Never use `# type: ignore` — fix the underlying type mismatch instead. If a value flows through the system as `str` but the destination expects `Literal["a", "b", "c"]`, type the entire chain with the Literal, don't suppress the error at the assignment. `type: ignore` hides real bugs.

### Regex patterns
- Use `\b` word boundaries when matching keywords that could appear as substrings of other words (e.g., `\bchange:` not `change:` — the latter matches `exchange:`).

### Error messages
- Include the actual error from stderr/exceptions in error messages, not a generic description. `"Issue #42: gh failed (exit 1): auth required"` not `"Issue #42 not found"`.

### Validation ordering
- Validate prerequisites before performing operations that depend on them. Check that CLIs exist before calling them. Check that files/dirs exist before reading them.

### Consistency
- When adding a new function that does I/O, match the error handling pattern of existing functions in the same module. If the module wraps `read_text()` in `try/except (OSError, UnicodeDecodeError)`, new file reads in that module need it too.

### DRY
- Before writing a utility function, search for existing implementations (`grep -rn 'def function_name' src/`). Import from the canonical location, don't copy.

### Preview fidelity
- `--dry-run` output must match what the pipeline would actually produce. If the PR title in dry-run says `[harness] prompt-fix-bug` but the actual PR says `[harness] Fix the bug`, the preview is misleading.

## HARNESS.md convention

`HARNESS.md` is a per-repo file that provides instructions to autonomous harness workers. It lives in the target repo root and is read at worker dispatch time, injected into the worker's system prompt under a `## Repo-Specific Instructions` header.

**What belongs in HARNESS.md:**
- Eval commands and test instructions for autonomous workers
- Skill invocations the worker should use (e.g., `opsx:apply`)
- Retry hints for flaky tests or known issues
- Path restrictions or files to avoid
- Migration context or temporary workarounds
- Any guidance specific to autonomous (unattended) execution

**What does NOT belong in HARNESS.md:**
- General project context → put in `CLAUDE.md` (read by Claude Code natively for all sessions)
- Agent capability descriptions → put in `AGENTS.md`
- Build/test commands for interactive use → put in `CLAUDE.md`

**Guidelines:**
- Keep it under ~500 lines — it consumes context window for every worker dispatch
- HARNESS.md is additive — CLAUDE.md still applies via Claude Code's native loading
- Content is injected verbatim as freeform markdown, no special syntax required

## OpenSpec workflow

All features follow the OpenSpec lifecycle:

```
propose → [resolve prerequisites] → implement → self-validate → archive
```

See `openspec/ROADMAP.md` for the current change sequence.
