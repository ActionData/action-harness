## Context

`_build_pr_body` currently takes only `change_name` and `eval_result`. The pipeline has richer data available — the `WorkerResult` (with cost, duration, output), the worktree (where we can run `git diff --stat` and `git log`), and the repo (where we can read the proposal). None of this reaches the PR body.

## Goals / Non-Goals

**Goals:**
- PR body gives a reviewer enough context to understand the change without reading the diff blind
- All data comes from what the pipeline already has — no extra LLM calls
- Body is structured markdown that renders well on GitHub

**Non-Goals:**
- LLM-generated summaries of the diff (no extra Claude calls)
- Inline review comments on the PR
- PR labels or assignees

## Decisions

### 1. Read proposal summary from the change directory

Read `openspec/changes/<name>/proposal.md` from the worktree and extract the "Why" section. This gives the reviewer the motivation without needing to find the spec. If the file doesn't exist or can't be parsed, omit the section gracefully.

**Why:** The proposal is the most concise context about what the change is for. It's already written and available in the worktree.

### 2. Run git commands in the worktree to get diff stat and commit log

Run `git diff --stat origin/<base>..HEAD` and `git log --oneline origin/<base>..HEAD` in the worktree to get file-level changes and commit messages. Use `origin/<base>` because the worktree may not have a local ref for the base branch — it was branched from the remote tracking ref.

**Why:** The diff stat shows scope (how many files, how many lines). The commit log shows the worker's incremental progress.

### 3. Thread WorkerResult through to create_pr

Add `worker_result: WorkerResult` as a parameter to `create_pr` and `_build_pr_body`. Include cost, duration, and worker observations if available.

**Why:** Cost and duration are useful for the operator. Worker observations (the self-test output) provide qualitative context about what the worker tried.

### 4. Truncate long sections

Worker output and diff stat can be long. Truncate worker output to 500 chars and diff stat to 30 lines. Append `\n... (truncated)` when truncation occurs. The full details are in the diff itself.

**Why:** GitHub PR bodies have practical size limits and long bodies reduce readability.

## Risks / Trade-offs

**[Risk] Proposal file might not exist or have unexpected format.**
→ Mitigation: Gracefully omit the section. Use a simple regex or line scan for "## Why" — don't over-parse.

**[Trade-off] More subprocess calls during PR creation.**
→ Acceptable. Two git commands (~10ms each) for significantly better PR context.
