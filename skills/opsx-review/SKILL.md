---
name: opsx-review
description: Review new or changed OpenSpec artifacts using the spec-writer agent. Use when the user wants a quality review of proposals, specs, designs, or tasks.
license: MIT
compatibility: Requires openspec CLI.
metadata:
  author: openspec
  version: "1.0"
  generatedBy: "1.2.0"
---

Review OpenSpec artifacts for quality, completeness, and agent-implementability by launching a spec-writer agent.

**Input**: Optionally specify a change name. If omitted, auto-detect from context or review all changed openspec files.

## Steps

1. **Identify what to review**

   If a change name is provided (via `$ARGUMENTS`), review its artifacts directly under `openspec/changes/<name>/`.

   If no change name is provided, detect changed openspec files:
   ```bash
   # Staged + unstaged changes
   git diff --name-only HEAD -- openspec/
   # Untracked openspec files
   git ls-files --others --exclude-standard openspec/
   ```

   Combine and deduplicate the file lists. If no openspec files are found, tell the user and stop.

   If the files belong to a specific change (under `openspec/changes/<name>/`), extract the change name.

2. **Gather context**

   If a change name was identified:
   ```bash
   openspec status --change "<name>" --json
   ```

   Collect all artifact paths to review:
   - `openspec/changes/<name>/proposal.md`
   - `openspec/changes/<name>/design.md`
   - `openspec/changes/<name>/tasks.md`
   - `openspec/changes/<name>/specs/**/*.md`
   - Any main specs in `openspec/specs/` referenced by the change

3. **Launch spec-writer agent**

   Launch a single Agent with `subagent_type: "spec-writer"` and the following prompt:

   ```
   Review the OpenSpec artifacts for change "<name>" in this repository.

   Start by reading CLAUDE.md, then read these artifact files:
   <list of file paths>

   Also read any main specs in openspec/specs/ that are referenced by the change specs.

   Perform a thorough review covering:
   - Proposal quality: Is the "why" compelling? Are capabilities correctly identified?
   - Spec precision: Do requirements use SHALL/MUST? Does every requirement have scenarios with WHEN/THEN? Are THEN clauses specific enough?
   - Design decisions: Is there rationale? Were alternatives considered? Are risks identified?
   - Task decomposition: Are tasks small enough for one agent session? Ordered by dependency? Clear completion criteria?
   - Self-validation: Is it runnable without human involvement? Are human prerequisites identified?
   - Agent-implementability: Are tasks specific (file paths, function names) or vague?
   - Assertion depth: Do test tasks specify exact assertions, not just "verify it works"?
   - Test-spec traceability: Can every spec scenario map to a test task?
   - Capability coverage: Are edge cases, error paths, and boundaries covered?
   - Spec-implementation alignment: Do delta specs correctly reference main specs?

   Report each finding in this format:

   **{severity}: {title}**
   Artifact: {proposal|spec|design|tasks}

   {What's wrong and why it matters for agent-implementability.}
   Recommendation: {specific fix}

   Severity levels:
   - high: Agent will get stuck or build the wrong thing
   - medium: Ambiguity that may cause rework
   - low: Polish that improves clarity

   End with a summary: count of findings by severity and an overall assessment.
   ```

4. **Present findings**

   Display the agent's review results to the user.

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
- Do NOT attempt to fix findings — just report them
