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

- [x] `focused-fix-retry` — Cap and prioritize findings per fix-retry (`--max-findings-per-retry`). Cross-agent agreement scoring.
- [x] `spec-compliance-review` — 4th review agent verifying task descriptions match implementation diff.
- [x] `agent-knowledge-catalog` — 10-entry YAML catalog with ecosystem filtering, worker/reviewer prompt injection, per-repo finding frequency.
- [x] `agent-definitions` — Agent prompts loaded from `.harness/agents/*.md` files with per-repo override support.

- [x] `checkpoint-resume` — Pipeline checkpoints after each macro-stage. `--resume latest` picks up from last completed stage. Branch HEAD validation, CLI flag capture, atomic writes.

### Up next

1. `failure-reporting` — Aggregate failure logs, identify systemic patterns. Pairs with agent-knowledge-catalog: aggregate review findings across runs, identify which catalog rules fire most often, feed patterns back into the catalog.
3. `harness-dashboard` — Read-only CLI dashboard for onboarded repos, workspaces, and cross-repo OpenSpec state. Data layer (Pydantic models) designed for future TUI/web.
4. `live-progress-feed` — Real-time visibility into worker progress (task completion, file edits, tool calls) during pipeline runs. Needs specs.
5. `rollback-tags` — Git tag-based rollback points and shipped feature markers. Tags main branch before merge (`harness/pre-merge/{label}`) and after (`harness/shipped/{label}`). `harness rollback` reverts via revert commits. `harness history` lists shipped features. More valuable once auto-merge is routinely used.
6. `openspec-prerequisites` — Machine-readable prerequisites in `.openspec.yaml` (e.g., `prerequisites: [review-agents, protected-paths]`). `openspec ready` computes unblocked changes by traversing the dependency graph. Enables repo-lead to answer "what's ready to work on?" without parsing roadmap prose. Inspired by Beads `bd ready`. See `docs/research/gastown-comparison.md`.
7. `repo-lead` — Unified interactive + autonomous planning agent. `harness lead --repo <path> "prompt"` spawns a Claude Code session with repo context (roadmap, issues, catalog) to draft OpenSpec proposals, create issues, and optionally dispatch harness runs. Phase 1: on-demand for any repo. Phase 2: event-driven (GitHub issue triggers). Phase 3: scheduled triage. Same agent in all modes — only the trigger differs. See `docs/explore/repo-lead.md`.
8. `always-on` — Event-driven intake from webhooks, recurring maintenance, Slack escalation. Subsumes repo-lead Phase 2 (events) and Phase 3 (scheduled). Requires server mode, event loop.
9. `merge-queue` — Batch-then-bisect merge queue for concurrent pipeline runs. Rebase PRs as a stack, test the tip, bisect on failure. Prevents "all pass individually but conflict together" when repo-lead dispatches concurrent changes. Inspired by Gastown Refinery / Bors. Requires repo-lead + concurrent dispatch. See `docs/research/gastown-comparison.md`.
10. `ephemeral-observability` — Per-worktree observability stack (Vector → VictoriaLogs/Metrics/Traces) for target apps that emit telemetry. Lets workers query logs (LogsQL), metrics (PromQL), and traces (TraceQL) to validate runtime behavior — not just exit codes. Torn down when task completes. Requires repo-profiling to detect when a target app is a running service. Inspired by OpenAI's Codex harness architecture.
