## Context

The harness has a complete execution pipeline (worktree → worker → eval → review → PR → merge) and observability tools (report, dashboard, progress feed). What's missing is the planning layer — deciding *what* to work on. Today that's the human. The repo lead automates planning by giving a Claude Code session deep repo context.

See `docs/explore/repo-lead.md` for the full design exploration.

## Goals / Non-Goals

**Goals:**
- `harness lead --repo <path> "prompt"` CLI command
- Pre-load repo context: ROADMAP.md, CLAUDE.md, HARNESS.md, open issues (via `gh issue list`), assessment scores (via `harness assess`), recent run report (via `harness report`), catalog frequency data
- Agent persona in `.harness/agents/lead.md`
- Output: OpenSpec proposals, GitHub issues, or harness dispatch recommendations
- `--dispatch` flag to auto-dispatch recommended changes
- Handle repos without OpenSpec (bootstrap or `--prompt` fallback)

**Non-Goals:**
- Event-driven or scheduled operation (that's `always-on`)
- Continuous monitoring (the lead runs on-demand and exits)
- Cross-repo coordination (one lead per repo)
- Custom agent runtime (uses Claude Code CLI, not a new runtime)

## Decisions

### 1. Claude Code CLI dispatch, not a custom runtime

The lead is a Claude Code CLI invocation with a system prompt and pre-gathered context as the user prompt. Same pattern as worker dispatch but with a different persona and no eval/retry loop.

```
claude -p "<context + prompt>" \
  --system-prompt "<lead persona>" \
  --output-format json \
  --max-turns 50 \
  --permission-mode plan
```

Permission mode `default` allows the lead to read the codebase and run tools (gh issue list, openspec list, etc.) while prompting for approval on writes. This lets the lead gather information and produce a plan. The `--dispatch` flag handles execution — the lead recommends, the harness dispatches.

### 2. Context gathering as a pre-step

Before dispatching the lead, the harness gathers context:
1. Read ROADMAP.md, CLAUDE.md, HARNESS.md from the repo
2. Run `gh issue list --json title,body,labels,state --limit 20` for open issues
3. Run `harness assess --repo <path> --json` for assessment scores (if not too slow; cache recent results)
4. Read recent run report data from manifests
5. Read catalog frequency data from harness home

All context is assembled into a structured prompt section injected before the user's prompt.

### 3. Lead persona

The lead agent persona (`.harness/agents/lead.md`) describes the planning role:
- You are a technical lead for this repository
- You have full context of the repo's state, roadmap, issues, and quality metrics
- You can: draft OpenSpec proposals (opsx:propose), create issues (gh issue create), recommend harness dispatches, explore ideas (opsx:explore)
- You prioritize based on: roadmap order, issue severity, assessment gaps, failure patterns

### 4. `--dispatch` auto-dispatches recommended changes

When `--dispatch` is provided, the lead's output is parsed for recommended changes. For each recommendation, the harness dispatches `harness run --change <name> --repo <path>` as a subprocess. Only changes that already have OpenSpec artifacts are eligible for auto-dispatch.

### 5. Repos without OpenSpec

For repos that don't have `openspec/` initialized:
- The lead can run `openspec init` to bootstrap
- Or fall back to `--prompt` mode recommendations
- The lead's context still includes CLAUDE.md, issues, and assessment (these don't require OpenSpec)

### 6. Output format

The lead outputs a JSON plan:
```json
{
  "summary": "Recommended actions for this repo",
  "proposals": [
    {"name": "add-auth", "description": "...", "priority": "high"}
  ],
  "issues": [
    {"title": "Fix login timeout", "body": "...", "labels": ["bug"]}
  ],
  "dispatches": [
    {"change": "add-logging", "flags": ["--auto-merge"]}
  ]
}
```

In interactive mode, this is displayed as a formatted plan. With `--dispatch`, the dispatches are executed.

## Risks / Trade-offs

- [Context window] Gathering all context (roadmap, issues, assessment, report) may consume significant context → Mitigation: truncate or summarize large sections. Issues limited to 20. Assessment is one JSON object.
- [Lead quality] The lead's recommendations depend on repo context quality → Mitigation: assessment scores tell the lead what's missing. Low-context repos get "improve context" as the first recommendation.
- [Auto-dispatch safety] `--dispatch` runs changes without human approval → Mitigation: only pre-existing OpenSpec changes are eligible. Protected paths still trigger human review. Auto-merge gates still apply.
