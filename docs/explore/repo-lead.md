# Repo Lead — unified interactive + autonomous planning agent

## The idea

The repo lead is a Claude Code session with repo-specific context that can be driven by a human (interactive) or by events/schedules (autonomous). It's not a new agent type — it's a formalization of what already happens when you sit down with Claude Code in a repo and plan work. The difference is making it work for any onboarded repo, and making it runnable without a human at the keyboard.

```
Human (intent, judgment, taste)
  ↕
Repo Lead (interactive OR autonomous)
  ↕
action-harness (execution pipeline)
  ↕
Target repositories
```

## Same agent, two modes

Interactive and autonomous modes are the same Claude Code session with the same context. The only difference is who provides the initial prompt.

| Mode | Trigger | Initial prompt |
|---|---|---|
| Interactive | Human opens session | Whatever you say |
| Event-driven | GitHub issue, PR comment, Slack | Event payload formatted as prompt |
| Scheduled | Cron / harness scheduler | "Triage open issues and suggest priorities" |

Same capabilities in all modes:
- Read repo state (ROADMAP.md, CLAUDE.md, HARNESS.md, open issues, codebase, catalog)
- Draft OpenSpec proposals (opsx:propose)
- Create GitHub issues
- Dispatch harness runs
- Suggest priorities
- Explore ideas (opsx:explore)

## Phased rollout

### Phase 1: On-demand for any repo

`harness lead --repo <path> "description"`

Spawns a Claude Code session with repo-lead context loaded. Human provides the prompt. Lead reads repo state, drafts proposals, creates issues, optionally dispatches.

This is the smallest useful increment — extends what you already do in action-harness to any onboarded repo.

### Phase 2: Event-driven (GitHub issues)

New GitHub issue → harness spawns a lead session with the issue as context. Lead reads the issue, assesses the repo, and either:
- Dispatches directly (clear, safe work)
- Creates an OpenSpec proposal first (needs design)
- Comments asking for clarification (ambiguous)

Builds on `github-issue-intake` but adds the judgment layer.

### Phase 3: Scheduled triage

Periodic lead sessions that look at repo state and suggest work:
- Open issues (unfiled, stale)
- Failing tests
- Roadmap gaps
- Catalog failure patterns
- TODOs/FIXMEs

Reports to operator via Slack, email, or CLI output.

## Architecture

The lead is not in the execution pipeline. It sits above it.

```
Planning plane (LLM — repo lead)
├── Reads repo context
├── Produces OpenSpec proposals, GitHub issues
├── Dispatches harness runs (when safe)
└── Reports to operator

Execution plane (deterministic — harness run)
├── worktree → worker → eval → retry → PR
├── review agents (quality gates)
├── openspec review (lifecycle gate)
└── auto-merge (if enabled)

Observation plane (read-only)
├── harness-dashboard
├── failure-reporting
└── (future) health monitoring
```

## Auto-dispatch safety

When the lead dispatches autonomously, it follows the same safety model as auto-merge:
- Protected paths → human review required
- New OpenSpec proposals → review agent validates first
- Leaf changes with good test coverage → safe for auto-dispatch
- Core pipeline changes → human approval

The lead recommends a dispatch mode (auto vs human-review) but the harness enforces the gates.

## Multi-repo

Start with one lead per repo. Each lead has deep context for its repo. For repos that relate to each other, a higher-level lead can coordinate — but this is configurable, not default. Most repos are independent.

```
Global lead (optional, configured)
├── Reads cross-repo state
├── Prioritizes across repos
└── Delegates to per-repo leads

Per-repo lead (default)
├── Deep repo context
├── Plans and dispatches for one repo
└── Independent of other repos
```

## Why this isn't a "Mayor"

The Gastown Mayor is a persistent coordinator that runs continuously and manages other agents. The repo lead is simpler:
- It's a Claude Code session, not a custom agent runtime
- It runs on-demand or triggered, not continuously (until Phase 3)
- It produces artifacts (proposals, issues), not runtime coordination decisions
- The harness pipeline is the coordinator, not the lead

The lead plans. The harness executes. The human steers.

## Relationship to existing roadmap items

- `always-on` — Phase 2 (event-driven) and Phase 3 (scheduled) are subsets of always-on
- `github-issue-intake` — Phase 2 builds on this, adding judgment before dispatch
- `agent-definitions` — lead prompt lives in `.harness/agents/lead.md`, same override pattern
- `harness-dashboard` — lead benefits from visibility into repo state
- `failure-reporting` + `agent-knowledge-catalog` — lead uses these for triage context
