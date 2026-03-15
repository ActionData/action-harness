## Context

The `session-resume` change uses `--resume` for retry continuity when the context window is fresh. This change provides the fallback path: when `--resume` isn't available (expired session, context >60%, CLI failure), a progress file in the worktree gives the fresh worker curated context about prior attempts.

The Anthropic harness article describes `claude-progress.txt` as cross-session memory. The harness equivalent is `.harness-progress.md` — written by the harness (not the worker) after each dispatch, read by the worker at the start of the next dispatch.

## Goals / Non-Goals

**Goals:**
- Write `.harness-progress.md` in the worktree after each worker dispatch + eval cycle
- Include structured information: attempt number, commits made, eval results, feedback given
- Worker reads the file at dispatch start (via prompt injection)
- Run eval before the worker on retries (pre-work verification)
- File accumulates across retries (append, not overwrite)

**Non-Goals:**
- Replacing `--resume` (this is the fallback, not the primary path)
- Worker writing to the progress file (the harness owns it — deterministic, not LLM-generated)
- Progress across pipeline runs (this is within a single pipeline run's retry loop)
- Task-level regression tracking (future enhancement)
- Progress files during review fix-retry dispatches (only the main eval retry loop)
- Interaction with `session-resume` — this change is independent and additive

## Decisions

### 1. Harness writes the progress file, not the worker

The progress file is written by the harness (deterministic Python code), not by the worker (LLM). This ensures the content is accurate, structured, and not subject to hallucination. The worker reads it but never modifies it.

**Alternative considered:** Having the worker write its own progress notes (like the Anthropic article's pattern). Rejected — the harness has ground-truth data (commits, eval exit codes, timing) that the worker doesn't. The harness can produce a more reliable summary.

### 2. Progress file format

```markdown
# Harness Progress

## Attempt 1
- **Commits**: 3 commits on branch harness/add-logging
- **Eval result**: FAILED — ruff check: 2 errors (unused import line 5, line too long line 42)
- **Feedback given**: <eval error output>
- **Duration**: 45.2s
- **Cost**: $0.23

## Attempt 2
- **Commits**: 1 additional commit (fix lint errors)
- **Eval result**: FAILED — mypy: missing type annotation on line 18
- **Feedback given**: <eval error output>
- **Duration**: 22.1s
- **Cost**: $0.11
```

Markdown is chosen because the worker (an LLM) reads it naturally. Each attempt is appended as a new section.

### 3. Injected into worker prompt, not system prompt

The progress file contents are appended to the worker's user prompt (not system prompt) when it exists. This positions it as task-specific context rather than role instructions. On the first dispatch (no progress file), the prompt is unchanged.

**Alternative considered:** Having the worker read the file itself via its tools. Rejected — injecting it into the prompt guarantees the worker sees it immediately without spending tool calls finding and reading it.

### 4. Pre-work eval on retries

Before dispatching a retry worker, the harness runs eval in the worktree. If eval passes (a prior commit fixed the issue), the retry is unnecessary — skip straight to PR creation. If eval shows new failures beyond the original feedback, the worker gets both the original and new failure context.

This prevents the worker from compounding existing breakage and catches cases where a prior dispatch partially fixed the issue.

### 5. Progress file is gitignored

`.harness-progress.md` is added to the worktree's `.gitignore` (or excluded from commits). It's an operational artifact, not part of the deliverable. The worker should not commit it.

## Risks / Trade-offs

- [Prompt bloat] Progress file grows with each retry, consuming context → Mitigation: with max_retries=3, the file is at most 4 sections. Manageable within a 1M context window.
- [Pre-work eval cost] Running eval before the worker adds wall time → Mitigation: eval is typically fast (seconds for lint/typecheck). The saved cost of avoiding a wasted dispatch far exceeds the eval time.
- [Worker ignores progress] The worker might not use the progress file effectively → Mitigation: the prompt injection positions it prominently. If the worker ignores it, the eval gate still catches regressions.
