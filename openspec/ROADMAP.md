# Action-Harness Roadmap

Goal: self-hosting. Build the minimum loop by hand, then the harness builds everything else.

## Bootstrap (build by hand)

- `reframe-pipeline` — Minimum self-hosting loop: CLI intake → worktree → code agent (opsx:apply) → eval → retry → PR creation. Human reviews and merges.
- `agent-debuggability` — Design rules, result models, and CLI flags (--verbose, --dry-run) that make the harness observable and testable by agents. Prerequisite for reliable self-hosting.
- `pipeline-run-manifest` — Persist all stage results as JSON per run. Foundation for PR descriptions, review agents, and failure analysis.
- `worker-config` — CLI flags for --model, --effort, --max-budget-usd, --permission-mode. Additive, no signature conflicts.
- `enrich-pr-description` — Richer PR body built from the run manifest. Modifies create_pr signature.
- `openspec-review-agent` — Final gate agent: spec validation, semantic review, automated archival. Adds stage after PR creation.
- `workspace-management` — Clone repos from URLs, persistent workspaces, configurable harness home, clean command. Enables multi-repo use.

## Self-Hosted Backlog (harness builds these)

Priority order. Each is an OpenSpec change the harness implements on itself.

1. `session-resume` — Use `--resume <session_id>` for eval retries and review fix-retry so workers retain full context across dispatches. Context-aware: resumes when context is fresh (<60% used), falls back to fresh dispatch when exhausted. Graceful fallback if resume fails. See `docs/explore/same-context-fix-retry.md`.
2. `retry-progress` — Write `.harness-progress.md` in worktree between retries (commits, eval results, what was tried). Workers read it for curated cross-dispatch context. Pre-work eval on retries catches already-fixed issues before dispatching. Fallback for when `--resume` isn't available. Inspired by Anthropic's harness patterns article. See `docs/research/long-running-agent-harness-patterns.md`.
3. `structured-logging` — JSON logs for phase transitions, dispatches, eval results
4. `review-agents` — Bug hunter, test reviewer, quality reviewer as independent Claude Code dispatches
5. `protected-paths` — Guardrails: files/modules that always escalate to human review
6. `auto-merge` — Merge after review agents approve + CI passes (requires review-agents, protected-paths)
7. `harness-md` — Per-repo `HARNESS.md` file convention for autonomous worker instructions. Read at dispatch time, injected into system prompt. May include a `## Setup` section with commands the harness executes before worker dispatch (boot dev server, install deps). Requires workspace-management for multi-repo use. See `docs/research/long-running-agent-harness-patterns.md` for the `init.sh` pattern this draws from.
8. `repo-profiling` — Detect eval capabilities and context quality before dispatch (needed for other repos). Runs once at repo onboard (requires workspace-management), not on every pipeline run. Also prescriptive: identify gaps and propose changes to fill them. Gaps that block the harness (no tests, no structured logging, no observability for services) are flagged as prerequisites. Gaps that improve quality but don't block (no CI config, no README, no type checking) are flagged as recommendations.
9. `codebase-assessment` — `harness assess` command that scores a repo's agentic readiness across categories (context, testability, CI guardrails, observability, tooling, isolation). Three modes: base mechanical scan (`--repo`), agent-enriched quality assessment (`--deep`), and auto-generated OpenSpec proposals for each gap (`--propose`). Builds on repo-profiling signals. Assessment agent is read-only; spec-writer agents generate proposals in parallel.
10. `github-issue-intake` — Parse GitHub issues for OpenSpec references, dispatch from issues
11. `unspecced-tasks` — `--prompt` flag on `harness run` for freeform tasks without a full OpenSpec change. Worker receives the prompt directly instead of opsx:apply. Everything else (worktree, eval, PR, review agents) stays the same. OpenSpec review skipped.
12. `failure-reporting` — Aggregate failure logs, identify systemic patterns
13. `always-on` — Event-driven intake from webhooks, recurring maintenance, Slack escalation
14. `checkpoint-resume` — Checkpoint pipeline state so interrupted runs can resume from the last completed stage. Distinct from `retry-progress` which handles within-stage retry continuity — this is about cross-stage resumption after process crashes. Needs specs.
15. `live-progress-feed` — Real-time visibility into worker progress (task completion, file edits, tool calls) during pipeline runs. Needs specs.
16. `rollback-tags` — Git tag-based rollback points and shipped feature markers. Tags main branch before merge (`harness/pre-merge/{label}`) and after (`harness/shipped/{label}`). `harness rollback` reverts via revert commits. `harness history` lists shipped features. Requires auto-merge for inline post-merge tagging.
17. `ephemeral-observability` — Per-worktree observability stack (Vector → VictoriaLogs/Metrics/Traces) for target apps that emit telemetry. Lets workers query logs (LogsQL), metrics (PromQL), and traces (TraceQL) to validate runtime behavior — not just exit codes. Torn down when task completes. Requires repo-profiling to detect when a target app is a running service. Inspired by OpenAI's Codex harness architecture.
