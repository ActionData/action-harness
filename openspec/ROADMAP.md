# Action-Harness Roadmap

Goal: self-hosting. Build the minimum loop by hand, then the harness builds everything else.

## Bootstrap (build by hand) ✓

All bootstrap items are complete.

- [x] `reframe-pipeline` — Minimum self-hosting loop: CLI intake → worktree → code agent (opsx:apply) → eval → retry → PR creation. Human reviews and merges.
- [x] `agent-debuggability` — Design rules, result models, and CLI flags (--verbose, --dry-run) that make the harness observable and testable by agents. Prerequisite for reliable self-hosting.
- [x] `pipeline-run-manifest` — Persist all stage results as JSON per run. Foundation for PR descriptions, review agents, and failure analysis.
- [x] `worker-config` — CLI flags for --model, --effort, --max-budget-usd, --permission-mode. Additive, no signature conflicts.
- [x] `enrich-pr-description` — Richer PR body built from the run manifest. Modifies create_pr signature.
- [x] `openspec-review-agent` — Final gate agent: spec validation, semantic review, automated archival. Adds stage after PR creation.
- [x] `workspace-management` — Clone repos from URLs, persistent workspaces, configurable harness home, clean command. Enables multi-repo use.

## Self-Hosted Backlog (harness builds these)

Priority order. Each is an OpenSpec change the harness implements on itself.

### Completed

- [x] `structured-logging` — JSON logs for phase transitions, dispatches, eval results
- [x] `review-agents` — Bug hunter, test reviewer, quality reviewer as independent Claude Code dispatches
- [x] `protected-paths` — Guardrails: files/modules that always escalate to human review
- [x] `repo-profiling` — Detect eval capabilities and context quality before dispatch. Prescriptive gap analysis with prerequisites and recommendations.
- [x] `session-resume` — Use `--resume <session_id>` for eval retries and review fix-retry so workers retain full context across dispatches. Context-aware: resumes when context is fresh (<60% used), falls back to fresh dispatch when exhausted. Graceful fallback if resume fails.
- [x] `retry-progress` — Write `.harness-progress.md` in worktree between retries (commits, eval results, what was tried). Workers read it for curated cross-dispatch context. Pre-work eval on retries catches already-fixed issues before dispatching. Fallback for when `--resume` isn't available.
- [x] `auto-merge` — Merge after review agents approve + CI passes. Opt-in via `--auto-merge` flag. Three gates: no protected files, review clean, openspec review passed. Optional `--wait-for-ci`.

### Up next

1. `review-tolerance` — Configurable review depth via tolerance levels (low/med/high) per round, acknowledgment protocol for declined findings, two-strike code comment escalation.
2. `harness-md` — Per-repo `HARNESS.md` file convention for autonomous worker instructions. Read at dispatch time, injected into system prompt. May include a `## Setup` section with commands the harness executes before worker dispatch (boot dev server, install deps). Requires workspace-management for multi-repo use. See `docs/research/long-running-agent-harness-patterns.md` for the `init.sh` pattern this draws from.
3. `codebase-assessment` — `harness assess` command that scores a repo's agentic readiness across categories (context, testability, CI guardrails, observability, tooling, isolation). Three modes: base mechanical scan (`--repo`), agent-enriched quality assessment (`--deep`), and auto-generated OpenSpec proposals for each gap (`--propose`). Builds on repo-profiling signals. Assessment agent is read-only; spec-writer agents generate proposals in parallel.
4. `unspecced-tasks` — `--prompt` flag on `harness run` for freeform tasks without a full OpenSpec change. Worker receives the prompt directly instead of opsx:apply. Everything else (worktree, eval, PR, review agents) stays the same. OpenSpec review skipped.
5. `github-issue-intake` — Parse GitHub issues for OpenSpec references, dispatch from issues. Depends on `unspecced-tasks` for `--prompt` fallback when issues don't reference an OpenSpec change.
6. `failure-reporting` — Aggregate failure logs, identify systemic patterns
7. `always-on` — Event-driven intake from webhooks, recurring maintenance, Slack escalation
8. `checkpoint-resume` — Checkpoint pipeline state so interrupted runs can resume from the last completed stage. Distinct from `retry-progress` which handles within-stage retry continuity — this is about cross-stage resumption after process crashes. Needs specs.
9. `live-progress-feed` — Real-time visibility into worker progress (task completion, file edits, tool calls) during pipeline runs. Needs specs.
10. `rollback-tags` — Git tag-based rollback points and shipped feature markers. Tags main branch before merge (`harness/pre-merge/{label}`) and after (`harness/shipped/{label}`). `harness rollback` reverts via revert commits. `harness history` lists shipped features. Requires auto-merge for inline post-merge tagging.
11. `ephemeral-observability` — Per-worktree observability stack (Vector → VictoriaLogs/Metrics/Traces) for target apps that emit telemetry. Lets workers query logs (LogsQL), metrics (PromQL), and traces (TraceQL) to validate runtime behavior — not just exit codes. Torn down when task completes. Requires repo-profiling to detect when a target app is a running service. Inspired by OpenAI's Codex harness architecture.
