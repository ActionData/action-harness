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

- [x] `harness-md` — Per-repo HARNESS.md file convention for autonomous worker instructions. Read at dispatch time, injected into system prompt.
- [x] `unspecced-tasks` — `--prompt` flag on `harness run` for freeform tasks without a full OpenSpec change. Worker receives the prompt directly. OpenSpec review skipped.
- [x] `github-issue-intake` — `--issue` flag to dispatch from GitHub issues. Detects OpenSpec change references, falls back to `--prompt` mode. PR links to issue for auto-closure. Status labels.
- [x] `codebase-assessment` — `harness assess` command scoring agentic readiness across 6 categories. Three modes: base scan, `--deep` agent assessment, `--propose` for auto-generated OpenSpec proposals.
- [x] `review-tolerance` — Configurable review depth via `--review-cycle` (low/med/high per round). Default: `low,med,high` (3 rounds, progressively stricter).

### Up next

1. `agent-knowledge-catalog` — Configurable review depth via tolerance levels (low/med/high) per round, acknowledgment protocol for declined findings, two-strike code comment escalation. Active bottleneck: review agents produce 13+ findings that can't be fully resolved in 2 fix-retry rounds.
2. `agent-knowledge-catalog` — Structured catalog of bug/quality issue classes (subprocess safety, type narrowing, regex patterns, error clarity, etc.) with per-entry rules for workers, checklists for reviewers, and scoring criteria for assessment. Filtered by ecosystem (Python, JS, Rust). Three-layer context hierarchy: universal → ecosystem → repo-specific. Per-repo knowledge store for findings frequency. Self-improving: review findings seed new entries. Prevents bugs at the source — highest multiplier effect. See `docs/research/agent-quality-catalog.md`.
3. `failure-reporting` — Aggregate failure logs, identify systemic patterns. Pairs with agent-knowledge-catalog: aggregate review findings across runs, identify which catalog rules fire most often, feed patterns back into the catalog.
4. `checkpoint-resume` — Checkpoint pipeline state so interrupted runs can resume from the last completed stage. Distinct from `retry-progress` which handles within-stage retry continuity — this is about cross-stage resumption after process crashes. Needs specs.
5. `harness-dashboard` — Read-only CLI dashboard for onboarded repos, workspaces, and cross-repo OpenSpec state. Data layer (Pydantic models) designed for future TUI/web.
6. `live-progress-feed` — Real-time visibility into worker progress (task completion, file edits, tool calls) during pipeline runs. Needs specs.
7. `rollback-tags` — Git tag-based rollback points and shipped feature markers. Tags main branch before merge (`harness/pre-merge/{label}`) and after (`harness/shipped/{label}`). `harness rollback` reverts via revert commits. `harness history` lists shipped features. More valuable once auto-merge is routinely used.
8. `always-on` — Event-driven intake from webhooks, recurring maintenance, Slack escalation. Big scope — requires server mode, event loop. Deferred until core quality loop is solid.
9. `ephemeral-observability` — Per-worktree observability stack (Vector → VictoriaLogs/Metrics/Traces) for target apps that emit telemetry. Lets workers query logs (LogsQL), metrics (PromQL), and traces (TraceQL) to validate runtime behavior — not just exit codes. Torn down when task completes. Requires repo-profiling to detect when a target app is a running service. Inspired by OpenAI's Codex harness architecture.
