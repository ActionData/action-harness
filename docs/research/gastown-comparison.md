# Gastown comparison and takeaways

Source: [steveyegge/gastown](https://github.com/steveyegge/gastown) — a multi-agent orchestration system for Claude Code by Steve Yegge.

## What Gastown is

A "town" of persistent AI agents coordinated by a Mayor agent. Written in Go with significant infrastructure (Dolt SQL server, daemon system, Git-backed issue tracking). Designed for multi-agent concurrent work across multiple repos.

Key agents:
- **Mayor** — LLM coordinator. Breaks down requests into tasks, spawns agents, monitors progress.
- **Polecats** — Worker agents with persistent identity. Work in isolated worktrees. Submit to merge queue.
- **Witness** — Monitors polecat health per-rig, detects stuck agents, nudges or escalates.
- **Deacon** — Daemon beacon. Continuous patrol cycles for system health, heartbeats, recovery.
- **Refinery** — Merge queue processor. Batch-then-bisect testing, conflict resolution, quality gates.
- **Crew** — Long-lived named agents for persistent collaboration (like "deputy Mayors").

Work tracking via "Beads" — a SQL-backed issue system with Git backing, prefix-based routing across repos, and structured fields. Work assigned via "slinging" beads to agent "hooks."

## Architectural comparison

| Dimension | action-harness | Gastown |
|---|---|---|
| Orchestration | Deterministic (zero LLM in control plane) | LLM-based (Mayor coordinates) |
| Workers | Stateless, fresh each dispatch | Persistent identity (Polecats) |
| State | Filesystem + JSON manifests | Dolt SQL + Git-backed Beads |
| Work tracking | OpenSpec changes + GitHub issues | Beads (custom SQL-backed issues) |
| Eval | Subprocess exit codes | Configurable gates in Refinery |
| Merge | Single-PR auto-merge | Batch-then-bisect merge queue |
| Review | 4 specialized review agents | Witness health monitoring |
| Monitoring | Event log + structured logging | Deacon daemon with patrols |
| Scale | Sequential pipeline, growing multi-repo | Concurrent multi-agent, multi-repo |
| Complexity | ~17K lines Python, minimal deps | Go + Dolt + daemon infrastructure |

## Shared beliefs

- Git worktrees for isolation (every task gets its own)
- Claude Code as the agent runtime (dispatch via CLI, no custom LLM client)
- External evaluation (agents don't grade own work, exit codes are the gate)
- Configurable quality gates (define what commands to run)
- Session continuity for context exhaustion (session-resume / handoff)

## Patterns worth adopting

### 1. Repo Mayor (planning plane)

Gastown's Mayor is an LLM coordinator that breaks down requests, spawns agents, and monitors. For action-harness, a constrained version: an LLM that does *intake and planning* — drafting OpenSpec proposals from vague intent, creating GitHub issues, suggesting priorities from roadmap state — without replacing deterministic orchestration.

This separates the planning plane (LLM) from the execution plane (deterministic pipeline). The Mayor produces structured work items that the harness executes mechanically.

Connects to: `always-on` roadmap item. Instead of just responding to webhooks, the Mayor proactively looks at the repo and suggests work.

### 2. Batch-then-bisect merge queue (Refinery)

When multiple PRs land around the same time:
1. Rebase all as a stack onto main
2. Test the tip (tests everything below for free)
3. If tip passes → fast-forward merge all
4. If tip fails → binary bisect to find the culprit in log2(N) test runs

Matters when: concurrent pipeline runs produce multiple PRs that each pass individually but conflict when combined.

Connects to: `auto-merge` evolution. Currently a pass/fail gate, could become a merge queue.

### 3. Witness/Deacon separation (health monitoring)

Deacon = system health ("is the harness running? is disk full?"). Witness = task health ("is this pipeline stuck? has this worker been silent for 20 minutes?"). Separating these avoids one agent trying to do both.

Connects to: `always-on` and `checkpoint-resume` roadmap items. Deacon maps to system monitoring, Witness maps to interrupted run detection.

### 4. Capability Ledger → success tracking in catalog

Gastown tracks every agent completion in a permanent ledger. For action-harness, extending the `agent-knowledge-catalog` with success data: resolution rates, first-attempt compliance rates per rule. This creates a feedback loop — rules that workers consistently get wrong signal that the worker prompt needs better guidance, not just the reviewer checklist.

Connects to: `agent-knowledge-catalog` and `agent-definitions` (catalog could inject "pay special attention to X" into worker prompts based on repo-specific failure patterns).

## Patterns we don't need (yet)

### Persistent worker identity (Polecats)

Gastown needs identity because workers run concurrently and need monitoring. action-harness runs sequentially — session-resume gives continuity, RunManifest gives attribution. Identity overhead isn't justified until concurrent pipeline instances.

### Custom issue tracking (Beads)

SQL-backed structured issues with prefix routing. action-harness uses OpenSpec changes + GitHub issues, which provides enough structure. The harness-dashboard change gives visibility without building a custom issue system.

### LLM orchestration in the control plane

Mayor makes runtime coordination decisions. action-harness keeps orchestration deterministic (testable, debuggable, no cascading LLM errors). The repo Mayor idea adds LLM to the planning plane only, not the execution plane.
