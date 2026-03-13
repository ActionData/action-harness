## Context

The harness pipeline currently: worktree → worker → eval → PR. The worker runs `opsx:apply` which checks off tasks, but nothing validates that the OpenSpec lifecycle is complete. No one checks that delta specs are well-formed, that the implementation actually matches the spec intent, or that completed changes are archived. Today this is manual — a human runs `/opsx:archive` after merging.

The self-hosted backlog includes `review-agents` (#2) as code reviewers (bug-hunter, test-reviewer, quality-reviewer). The OpenSpec review agent is a different kind of reviewer — it reviews the spec lifecycle, not the code. It should run as the final gate, after code reviewers (when they exist) or after eval (for now).

## Goals / Non-Goals

**Goals:**
- Validate task completion: all tasks in `tasks.md` are checked `[x]`
- Validate delta spec structure: run `openspec validate <change>` and check for errors
- Semantic review: does the implementation (the diff) match what the spec describes?
- Archive completed changes: run the archive process and push results to the PR branch
- Report findings if the implementation has gaps relative to the spec

**Non-Goals:**
- Code quality review (that's bug-hunter, test-reviewer, quality-reviewer)
- Modifying implementation code (this agent reviews and archives, it doesn't fix)
- Writing new specs (the spec was written before implementation)

## Decisions

### 1. Dispatch as a Claude Code worker with OpenSpec-specific system prompt

The OpenSpec reviewer is dispatched the same way as the code worker — via `claude` CLI subprocess in the worktree. It receives a system prompt that instructs it to:
1. Read the change's spec and task artifacts
2. Read the PR diff
3. Validate task completion
4. Run `openspec validate <change>`
5. Perform semantic review (do the code changes match the spec requirements?)
6. If satisfied, run `openspec archive <change> -y`
7. Commit and report findings

**Why:** Same dispatch mechanism as the code worker. No new infrastructure needed. The agent has full repo access in the worktree.

### 2. The agent runs in the same worktree as the code worker

The PR branch worktree already has the implementation. The OpenSpec agent works in the same worktree — it reads specs, runs validation, and if archiving, commits the archive changes on the same branch.

**Why:** The archive changes (moved files, updated main specs) should be part of the same PR. One atomic merge includes both implementation and spec updates.

### 3. DeepWiki access for OpenSpec documentation

The agent's system prompt includes a reference to `Fission-AI/OpenSpec` on deepwiki for understanding delta spec rules, archive semantics, and validation requirements. This gives it authoritative knowledge about the OpenSpec system without embedding all the docs in the prompt.

**Why:** The agent needs to understand OpenSpec conventions (ADDED/MODIFIED/REMOVED/RENAMED semantics, archive process, validation rules) to do semantic review. DeepWiki provides this without bloating the system prompt.

### 4. Findings format: approve or return with questions

The agent produces one of two outcomes:
- **Approve**: all validations pass, archive complete, changes pushed. Returns success.
- **Findings**: list of issues (incomplete tasks, spec violations, implementation gaps). Returns failure with structured findings. The pipeline can retry or escalate.

**Why:** Binary outcome makes the pipeline logic simple. Findings are structured so a retry dispatch can include them as feedback.

### 5. Pipeline placement: after PR creation

The OpenSpec reviewer runs after the PR is created. It validates, archives, and pushes the archive commit to the PR branch. When code review agents are added later, the OpenSpec reviewer runs after them.

```
Bootstrap:  worker → eval → PR → openspec-review (archive + push) → human merges
Future:     worker → eval → PR → code-reviews → openspec-review (archive + push) → merge
```

**Why:** The PR must exist first so the archive changes can be pushed to the same branch. The reviewer is the final gate before merge.

### 6. Agent output format

The review agent's system prompt instructs it to output a structured JSON block as its final message:

```json
{
  "status": "approved" | "findings",
  "tasks_total": 5,
  "tasks_complete": 5,
  "validation_passed": true,
  "semantic_review_passed": true,
  "findings": [],
  "archived": true
}
```

The harness parses this from the worker's JSON output (`result` field). If parsing fails, treat as findings with a parse error.

**Why:** Structured output makes the result deterministic to parse. The agent can still produce free-text reasoning in its conversation, but the final JSON block is what the harness reads.

### 7. Semantic review is advisory, not blocking

Structural validation (task completion, `openspec validate`) is the hard gate. Semantic review (does the diff match spec intent?) is advisory — findings are included in the result but do not block archival if structural checks pass.

**Why:** Semantic review is an LLM judgment call and cannot be mechanically verified. Blocking on it would create false negatives. Over time, the agent's accuracy improves as specs become more precise.

### 8. No retry for the review agent

The OpenSpec review stage does not retry. If it returns findings, the pipeline reports failure. Re-dispatching the implementation worker with review findings as feedback is a future enhancement.

**Why:** Review findings typically require implementation changes, not re-running the reviewer. Retry logic for the review stage adds complexity without clear benefit at bootstrap.

## Risks / Trade-offs

**[Risk] Archive on the PR branch creates merge conflicts if main changed.**
→ Mitigation: The archive moves files and updates specs. If main has concurrent spec changes, git will flag conflicts on merge. This is the same risk as any long-lived branch. Keep branches short-lived.

**[Risk] Agent misinterprets spec intent during semantic review.**
→ Mitigation: The agent validates structure mechanically (via `openspec validate`) and does semantic review best-effort. Structural validation is the gate; semantic review is advisory. Over time, the agent's accuracy improves as specs become more precise.

**[Risk] Archiving partially complete changes.**
→ Mitigation: The agent checks task completion first. If tasks are incomplete, it reports findings instead of archiving. The `openspec archive` command also validates before proceeding.
