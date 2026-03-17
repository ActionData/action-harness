# Documentation Index

Research and exploration notes supporting action-harness development.

## Research

In-depth analysis of approaches, patterns, and prior art.

| Document | Summary |
|----------|---------|
| [`research/agent-quality-catalog.md`](research/agent-quality-catalog.md) | Knowledge catalog design for encoding recurring agent quality signals as reusable entries |
| [`research/ephemeral-observability-for-agents.md`](research/ephemeral-observability-for-agents.md) | Per-worktree observability stacks (Vector, VictoriaLogs/Metrics/Traces) for runtime validation |
| [`research/gastown-comparison.md`](research/gastown-comparison.md) | Comparison to Gastown's merge queue and refinery pattern for concurrent pipeline runs |
| [`research/long-running-agent-harness-patterns.md`](research/long-running-agent-harness-patterns.md) | Patterns for sustained autonomous operation: scheduling, health checks, escalation |

## Exploration

Early-stage thinking and design sketches for future capabilities.

| Document | Summary |
|----------|---------|
| [`explore/repo-lead.md`](explore/repo-lead.md) | Unified interactive + autonomous planning agent: on-demand, event-driven, and scheduled modes |
| [`explore/reproducible-agent-runtime.md`](explore/reproducible-agent-runtime.md) | Making agent execution deterministic and debuggable across dispatches |
| [`explore/same-context-fix-retry.md`](explore/same-context-fix-retry.md) | Retaining full context across retry cycles via session resume |
