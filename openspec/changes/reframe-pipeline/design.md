## Context

action-harness needs to reach self-hosting: the harness works on its own codebase. This change builds the minimum loop to get there. Everything else (review agents, auto-merge, observability) is a self-hosted task the harness builds for itself.

The key infrastructure already exists:
- **Claude Code** provides the agent runtime (file I/O, shell, planning, tool use, MCP)
- **OpenSpec workflow** (`opsx:propose`, `opsx:apply`, `opsx:archive`) provides structured task execution
- **GitHub** provides PRs and review infrastructure
- **The harness's own repo** has a solid eval suite (pytest, ruff, mypy) — the first target

## Goals / Non-Goals

**Goals:**
- Build the minimum loop: CLI → worktree → code agent → eval → retry → PR
- The harness can work on its own codebase using this loop
- Human reviews and merges PRs (safety net until review agents and protected paths exist)
- The test suite is robust enough to catch bad changes before self-hosting begins

**Non-Goals (deferred to self-hosted backlog):**
- Review agents — self-hosted task #2
- Auto-merge — self-hosted task #4 (requires review agents + protected paths)
- GitHub issue intake — self-hosted task #6
- Repo profiling — self-hosted task #5 (not needed when the target is the harness's own repo)
- Observability dashboard — self-hosted task #1
- Always-on server mode — self-hosted task #9
- General-purpose agent framework
- Multi-tenant operation

## Decisions

### 1. Claude Code CLI as the worker invocation method

Use `claude` CLI subprocess invocation for workers, not the Agent SDK.

**Why:** The CLI is battle-tested, supports all needed flags (`--allowedTools`, `--system-prompt`, `--max-turns`, `--output-format json`), and keeps the harness as simple subprocess management. If the CLI proves limiting, switching to the SDK is straightforward.

### 2. `opsx:apply` as the implementation primitive

The harness dispatches a Claude Code worker that runs `opsx:apply` on the target change. This reuses the existing structured implementation workflow.

**Why:** `opsx:apply` already handles reading specs, tracking task progress, and validating work. No need to build a separate implementation path.

### 3. Two-tier testing: external eval (gate) + behavioral self-test (best-effort)

Tier 1: the harness runs eval commands as subprocesses and checks exit codes — this is the gate. Tier 2: the agent prompt instructs the agent to exercise the feature — this is best-effort, captured in output, not a gate.

**Why:** External eval is reliable and verifiable. Behavioral self-testing can't be verified from the outside but still provides useful signal for the human reviewer.

### 4. Python for orchestration, minimal abstraction

The harness is a Python CLI (typer) that coordinates subprocesses. Functions that call `subprocess.run` and parse JSON output. No framework.

**Why:** The hard work happens inside Claude Code. The harness just needs to create a worktree, invoke Claude Code, run eval, and open a PR.

### 5. The test suite gates self-hosting

Before the harness starts working on itself, the test suite must be comprehensive enough to catch regressions. Every bootstrap component gets tests. If the tests are weak, the harness can merge changes that break itself.

**Why:** The test suite is the immune system. Without it, self-hosting is unsafe.

## Risks / Trade-offs

**[Risk] Bootstrap test coverage is insufficient** — If tests don't cover the core loop well, the harness can break itself once self-hosting begins.
→ Mitigation: Every bootstrap component gets unit tests. Integration test runs the full loop on a test fixture repo. Don't start self-hosting until coverage is solid.

**[Risk] CLI subprocess invocation is too coarse** — No streaming, no mid-run intervention.
→ Mitigation: Start with CLI. Switch to SDK if needed — the prompt interface is the same.

**[Risk] First self-hosted tasks fail repeatedly** — The harness might not be reliable enough on its own codebase.
→ Mitigation: Start with leaf changes (new log field, CLI flag). Build confidence before attempting changes to core dispatch or eval logic. Tag a recovery baseline before self-hosting begins.

**[Risk] Eval commands hardcoded for this repo** — Bootstrap only runs pytest/ruff/mypy. Won't generalize to other repos.
→ Mitigation: Acceptable for bootstrap. Repo profiling (self-hosted task #5) generalizes this later.
