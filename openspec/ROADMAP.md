# Action-Harness Roadmap

Vision: an autonomous engineering pipeline that orchestrates Claude Code workers through the full development lifecycle — from task intake to merge — with increasing levels of autonomy.

## Phase 0: Core Pipeline

- `core-pipeline` — Single-phase pipeline: Claude Code coder → subprocess eval → feedback → retry
  - CLI: `action-harness run "task description" --repo ./path`
  - Worktree isolation
  - Repo onboarding (auto-detect build/test/lint)
  - JSON state persistence
  - Guardrails (max iterations, max files, cost budget, timeout)
  - Validate CLI vs SDK for Claude Code invocation

## Phase 1: Multi-Phase Pipeline

- `multi-phase` — Full coder → eval → review pipeline
  - Smart dispatch (skip phases based on repo profile and change type)
  - PR manager (open PR, push updates)
  - Specialized review agents (bug hunter, quality, test coverage)
  - Review finding triage and auto-fix

## Phase 2: Planning & OpenSpec

- `openspec-integration` — Planning and OpenSpec-aware execution
  - Planner agent for complex goal decomposition
  - OpenSpec-aware task creation (read proposals, generate tasks)
  - Multi-task execution (dependency ordering, parallel where possible)

## Phase 3: Always-On

- `always-on` — Server mode with channel intake
  - Event loop with async task processing
  - GitHub webhook intake (issues, PR comments, CI failures)
  - Linear integration
  - Cron-based monitoring (watch for new issues, stale PRs)
  - Escalation protocol (auto-handle → notify lead → escalate to human)
