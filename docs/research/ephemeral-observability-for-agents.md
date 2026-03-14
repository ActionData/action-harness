# Ephemeral Observability for Agent Harnesses

Date: 2026-03-13

## Origin

OpenAI published details about their Codex harness architecture. Key insight: they give the agent a full per-worktree observability stack so it can validate runtime behavior, not just exit codes.

Source: OpenAI blog post on increasing application legibility for Codex.

## The Pattern

The agent doesn't just run tests — it starts the app, runs workloads, and queries logs/metrics/traces to validate its work. The observability stack is ephemeral: spun up per worktree, torn down when the task completes.

```
┌─────────────────────────────────────────────────────────┐
│  Per-worktree ephemeral observability                    │
│                                                         │
│  Target App                                             │
│    │  logs (HTTP)                                       │
│    │  metrics (OTLP)                                    │
│    │  traces (OTLP)                                     │
│    ▼                                                    │
│  Vector (telemetry router, Rust-based)                  │
│    │  fans out to:                                      │
│    ├──▶ Victoria Logs   → queryable via LogQL API       │
│    ├──▶ Victoria Metrics → queryable via PromQL API     │
│    └──▶ Victoria Traces  → queryable via TraceQL API    │
│                                                         │
│  Agent queries these APIs to validate runtime behavior  │
│  Everything torn down when task completes               │
└─────────────────────────────────────────────────────────┘
```

Separate from the Victoria stack, they also use Chrome DevTools Protocol (via MCP) for UI-level validation — DOM snapshots, screenshots, navigation. The agent can drive the app through user journeys and visually verify results.

## The Stack

| Component | Role | Notes |
|-----------|------|-------|
| Vector | Telemetry router | Rust, fast. Receives OTLP/HTTP from app, fans out to backends |
| Victoria Logs | Log storage | Single binary, no deps. LogQL queries |
| Victoria Metrics | Metrics storage | Single binary, no deps. PromQL queries |
| Victoria Traces | Trace storage | Single binary, no deps. TraceQL queries |
| Chrome DevTools Protocol | UI observability | DOM snapshots, screenshots, click-through flows via MCP |

All Victoria components are single binaries with no dependencies — ideal for ephemeral per-worktree use. No Grafana or human dashboards needed; the agent queries APIs directly.

The app emits telemetry via:
- HTTP (logs)
- OTLP — OpenTelemetry Protocol (metrics and traces)

## How This Maps to action-harness

Two distinct levels:

### Level 1: Harness observability (logging the pipeline itself)
Tracking what the harness does — stage transitions, worker dispatches, eval results. This is the `structured-logging` roadmap item. Separate concern from what OpenAI is describing.

### Level 2: Target app observability (what OpenAI is doing)
Giving the worker agent runtime signals from the target app. Only matters when:
- The target app runs as a service (not just a library/CLI)
- The target app emits telemetry (OTLP, structured logs)
- The task involves runtime behavior (perf, errors, flows)

For action-harness working on itself (a CLI tool) — not needed. For working on web apps and services — very valuable.

### When you need it vs when you don't

| Task type | Need observability stack? |
|-----------|--------------------------|
| "Add a --verbose flag" | No (unit tests suffice) |
| "Fix failing test" | No (pytest exit code) |
| "Fix 500 error on /api/checkout" | Yes (need logs) |
| "Reduce p99 latency below 200ms" | Yes (need metrics) |
| "Debug intermittent timeout" | Yes (need traces) |
| "Ensure no regressions in user flow" | Yes (need all three) |

## Key Decision: Harness Doesn't Provide — It Proposes

Rather than the harness providing an observability stack for every target repo, the harness should detect when a repo lacks observability and propose adding it.

This is a prescriptive extension of repo-profiling:

```
Passive profiling                 Prescriptive profiling
─────────────────                 ──────────────────────
✓ Has pytest → run tests          ✗ No structured logging
✓ Has ruff → run lint               → propose adding OTLP telemetry
✗ No type checker → skip mypy     ✗ No health endpoint
                                    → propose adding /healthz
                                  ✗ No docker-compose for local stack
                                    → propose adding Vector + Victoria
```

Gap categories:
- *Prerequisites* — block the harness from doing its job (no tests, no logging for a service, no observability). Flagged as required.
- *Recommendations* — improve quality but don't block (no CI config, no README, no type checking). Flagged as nice-to-have.

Profiling runs once at repo onboard (via workspace-management), not on every pipeline run.

## Roadmap Status

- Added `ephemeral-observability` as item 12 on the self-hosted backlog
- Updated `repo-profiling` (item 5) to include prescriptive gap detection with prerequisite vs recommendation labeling
- Both depend on `workspace-management` (onboard-time, not per-run)
