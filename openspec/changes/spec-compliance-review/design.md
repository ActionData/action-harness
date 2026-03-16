## Context

The harness dispatches 3 review agents: bug-hunter, test-reviewer, quality-reviewer. Each reviews the diff for different concerns. None checks whether the implementation matches the task spec. This gap let `match_findings` go uncalled despite the task explicitly requiring it.

## Goals / Non-Goals

**Goals:**
- New review agent type: `spec-compliance-reviewer`
- Agent receives tasks.md + diff + change artifacts as context
- For each `[x]` task, verify the diff contains evidence of implementation
- Findings use the same ReviewFinding model as other agents
- Works on any OpenSpec repo (reads standard artifacts)

**Non-Goals:**
- Replacing the OpenSpec review agent (that checks archive readiness, this checks implementation compliance)
- Verifying test correctness (that's test-reviewer's job)
- Checking code quality (that's quality-reviewer's job)
- Running during non-OpenSpec (prompt-mode) pipelines (no tasks.md to check)
- Diff truncation for large changes (v1: agent fetches full diff via `gh pr diff` and does its best with available context)

## Decisions

### 1. Same dispatch pattern with extended context

The spec-compliance-reviewer uses `dispatch_single_review` like other agents. The key difference: its user prompt includes the tasks.md content (and optionally spec files) in addition to the standard "Review PR #N" instruction. This requires `dispatch_single_review` to accept optional `extra_context: str | None` that gets appended to the user prompt. Other agents ignore this parameter (pass None).

The agent still fetches the diff itself via `gh pr diff` (like other agents). The diff is NOT injected into the prompt — it would be too large. Only the tasks.md and spec content are injected.

### 2. Only runs when a change name is available

In prompt mode (`--prompt`), there's no tasks.md. The spec-compliance-reviewer is skipped. This is consistent with how OpenSpec review is skipped for prompt mode.

### 3. Agent reads tasks.md and checks each `[x]` task

The system prompt instructs the agent to:
1. Parse tasks.md and identify all `[x]` tasks
2. For each task, read the description carefully
3. Search the diff for evidence that the described behavior was implemented
4. Flag tasks where the diff doesn't match the description

Evidence includes: function calls mentioned in the task appearing in the diff, parameters described in the task present in function signatures, test assertions matching what the task specifies.

### 4. Severity levels

- **critical**: Task describes a function call or integration that is completely absent from the diff (e.g., "call match_findings" but it's never imported or called)
- **high**: Task describes specific behavior but the implementation takes a shortcut (e.g., "filter by matching" but implementation adds everything without filtering)
- **medium**: Task describes a parameter or return value that doesn't match the implementation
- **low**: Task describes a test assertion that is weaker than specified

### 5. Agent prompt includes spec files for context

The agent gets not just tasks.md but also the proposal and spec files, so it understands the intent behind each task. This helps it distinguish between a legitimate deviation (the worker found a better approach) and a genuine skip.

## Risks / Trade-offs

- [False positives] The agent may flag tasks where the implementation is semantically correct but syntactically different from the description → Mitigation: the agent is an LLM and can reason about semantic equivalence. The prompt instructs it to look for evidence of implementation, not exact string matching.
- [Context window] tasks.md + diff + specs could be large for big changes → Mitigation: for very large changes (>500 lines of diff), truncate the diff to the files mentioned in the task descriptions.
- [Cost] Adding a 4th review agent increases the review cost by ~25% → Mitigation: the cost of missing a `match_findings`-style bug is much higher than one more agent dispatch. Can be disabled with a flag if needed.
