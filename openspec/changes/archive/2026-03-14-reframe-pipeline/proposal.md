## Why

The harness needs to reach self-hosting: the point where it can accept tasks for its own codebase, implement them, and open PRs for human review. Everything after that is a task the harness does for itself.

This means the first build should be the minimum viable loop — just enough to dispatch a code agent, run eval, retry on failure, and open a PR. No review agents, no auto-merge, no GitHub issue parsing. Those become the harness's own first tasks once the bootstrap loop works.

## What Changes

- Build the minimum self-hosting loop: CLI intake → worktree → code agent → eval → retry → PR
- Human reviews and merges (no auto-merge in bootstrap)
- The harness's own codebase is the first target repo
- Architecture emerges from implementation, but core invariants are non-negotiable: external eval, deterministic supervisor, worktree isolation
- Update CLAUDE.md and ROADMAP.md to reflect self-hosting as the organizing goal

## Capabilities

### New Capabilities

- `task-intake`: Accept an OpenSpec change name and repo path via CLI (`--change`, `--repo`). No GitHub issue parsing in bootstrap.
- `code-agent`: Create worktree, dispatch Claude Code CLI worker to run `opsx:apply`, run eval (pytest, ruff, mypy) as subprocesses, retry on failure with structured feedback, cap retries at 3.
- `pr-lifecycle`: Open a PR via `gh pr create` with structured title/body. Human reviews and merges.

### Deferred Capabilities (self-hosted backlog)

These are NOT in scope for the bootstrap. They become the harness's first self-hosted tasks:

- `review-loop`: Review agents, feedback iteration, auto-merge
- `repo-profile`: Eval detection, context quality validation, smart dispatch
- `github-issue-intake`: GitHub issue parsing, `openspec:` reference extraction
- `unspecced-tasks`: Tasks without OpenSpec changes
- `structured-logging`: JSON observability for the harness itself

## Impact

- Replaces the original `proposal.md` and `ROADMAP.md`
- `CLAUDE.md` updated to reflect self-hosting goal and workflow-first framing
- `PROJECT_VISION.md` is the northstar document
- `openspec/ROADMAP.md` becomes the self-hosted backlog
