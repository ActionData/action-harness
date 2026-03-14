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

1. `structured-logging` — JSON logs for phase transitions, dispatches, eval results
2. `review-agents` — Bug hunter, test reviewer, quality reviewer as independent Claude Code dispatches
3. `protected-paths` — Guardrails: files/modules that always escalate to human review
4. `auto-merge` — Merge after review agents approve + CI passes (requires review-agents, protected-paths)
5. `harness-md` — Per-repo `HARNESS.md` file convention for autonomous worker instructions. Read at dispatch time, injected into system prompt. Requires workspace-management for multi-repo use.
6. `repo-profiling` — Detect eval capabilities and context quality before dispatch (needed for other repos). Runs once at repo onboard (requires workspace-management), not on every pipeline run. Also prescriptive: identify gaps and propose changes to fill them. Gaps that block the harness (no tests, no structured logging, no observability for services) are flagged as prerequisites. Gaps that improve quality but don't block (no CI config, no README, no type checking) are flagged as recommendations.
7. `github-issue-intake` — Parse GitHub issues for OpenSpec references, dispatch from issues
8. `unspecced-tasks` — Support simple fixes from issue descriptions without OpenSpec changes
9. `failure-reporting` — Aggregate failure logs, identify systemic patterns
10. `always-on` — Event-driven intake from webhooks, recurring maintenance, Slack escalation
11. `checkpoint-resume` — Checkpoint pipeline state so interrupted runs can resume from the last completed stage. Needs specs.
12. `live-progress-feed` — Real-time visibility into worker progress (task completion, file edits, tool calls) during pipeline runs. Needs specs.
13. `ephemeral-observability` — Per-worktree observability stack (Vector → VictoriaLogs/Metrics/Traces) for target apps that emit telemetry. Lets workers query logs (LogsQL), metrics (PromQL), and traces (TraceQL) to validate runtime behavior — not just exit codes. Torn down when task completes. Requires repo-profiling to detect when a target app is a running service. Inspired by OpenAI's Codex harness architecture.
