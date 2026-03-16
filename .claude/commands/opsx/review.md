---
name: "OPSX: Review"
description: "Review new or changed OpenSpec artifacts using the spec-writer agent"
category: Workflow
tags: [workflow, review, openspec, quality]
---

Review OpenSpec artifacts for quality, completeness, and agent-implementability.

**Input**: Optionally specify a change name. If omitted, auto-detect from context or review all changed openspec files.

## How it works

1. **Identify what to review**

   If a change name is provided, review its artifacts directly:
   ```
   openspec/changes/<name>/
   ```

   If no change name is provided, detect changed openspec files:
   ```bash
   git diff --name-only HEAD  # staged + unstaged changes
   git ls-files --others --exclude-standard openspec/  # untracked openspec files
   ```

   Filter to only `openspec/` files. If no openspec files are found, tell the user and stop.

2. **Determine context**

   If the changed files belong to a specific change (under `openspec/changes/<name>/`), extract the change name and run:
   ```bash
   openspec status --change "<name>" --json
   ```

   Read any existing main specs referenced by the change (`openspec/specs/`).

3. **Launch spec-writer agent**

   **IMPORTANT: Always run review agents in foreground (do NOT use `run_in_background`).** The review results are needed immediately to present to the user. Background agents complete but their findings are difficult to extract from transcripts, leading to wasted retries.

   When reviewing multiple changes, launch them in parallel using multiple Agent tool calls in a single message (foreground parallel, not background).

   Launch a spec-writer agent with subagent_type "spec-writer" to perform the review. Include the spec-reviewer agent definition (`.claude/agents/spec-reviewer.md`) in the agent's prompt for evaluation criteria. The agent should:

   - Read CLAUDE.md for project conventions
   - Read `.claude/agents/spec-reviewer.md` for the review rubric
   - Read all the identified openspec artifacts
   - Read any referenced main specs in `openspec/specs/`
   - **Trace data flows** through the spec: for each requirement, follow the data from input to output and check for logic errors, false positives in matching criteria, and stale data leaking between iterations
   - **Check task-implementation alignment**: verify every function mentioned in a task would actually be called, look for shortcut temptation, verify parameter types thread correctly through call chains
   - Review following the full rubric: proposal quality, spec precision, design decisions, task decomposition, self-validation, agent-implementability, assertion depth, test-spec traceability, capability coverage, spec-implementation alignment, semantic correctness
   - Report findings with severity (high/medium/low), artifact, description, and recommendation

4. **Present findings**

   Show the agent's review findings to the user, organized by severity.

## Output format

```
## OpenSpec Review: <change-name>

### Findings

**high: <title>**
Artifact: <artifact>
<description>
Recommendation: <fix>

**medium: <title>**
...

### Summary
- N high, N medium, N low findings
- Overall assessment
```

## Guardrails

- This is a review skill — it reads and analyzes but does NOT modify artifacts
- Always read the actual files before reviewing — don't guess at contents
- If no openspec files are found to review, say so and stop
- The spec-writer agent does the heavy lifting — pass it the right context and let it work
