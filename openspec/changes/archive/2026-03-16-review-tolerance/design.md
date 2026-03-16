## Context

The review stage in `pipeline.py` currently runs a hardcoded 2-round review-fix loop. `triage_findings()` returns `True` if any findings exist regardless of severity, and the fix-retry worker receives all findings as feedback. There is no mechanism for the worker to acknowledge a finding without fixing it, and no cross-round memory of what was already considered.

The review agents (`review_agents.py`) dispatch three parallel Claude Code invocations, collect structured `ReviewFinding` objects, and format them as markdown feedback. The pipeline orchestrates the loop, posts PR comments, and pushes fix commits.

## Goals / Non-Goals

**Goals:**
- Configurable review depth via tolerance levels that filter which severities are actionable per round
- Operator-defined review cycles via `--review-cycle` CLI flag
- Accountability: every actionable finding gets a response (fix or explain)
- Escalation: findings flagged by two rounds without a fix get a code comment
- Short-circuit on clean reviews to avoid wasted cycles

**Non-Goals:**
- Changing what the review agents themselves look for or how they assign severity
- Auto-categorizing findings as "same concern" across rounds (worker uses judgment)
- Persisting acknowledgment history beyond a single pipeline run

## Decisions

### 1. Tolerance filters actionable findings, not reported findings

Review agents always report everything. Tolerance controls which findings are sent to the fix-retry worker as actionable. All findings are posted to the PR comment regardless.

**Rationale:** Full visibility for humans reviewing the PR. Tolerance is a cost optimization for worker cycles, not a suppression mechanism.

**Alternative considered:** Having agents only look for findings at or above the tolerance threshold. Rejected because it wastes the agent dispatch — you're already paying for the review, might as well get all the findings.

### 2. Review cycle as an ordered list of tolerance levels

The cycle is a `list[str]` like `["low", "med", "high"]`. Each element is a round. The pipeline iterates through the list, running review + fix-retry at each tolerance level. Default is `["low", "med", "high"]`.

**Rationale:** Simple, declarative, covers all use cases (strict: `["low", "low", "low"]`, quick: `["high"]`, balanced: `["low", "med", "high"]`). No special configuration format needed — just a comma-separated CLI flag.

**Alternative considered:** A structured config with per-round settings (agents to run, max retries per round, etc.). Rejected as over-engineering — tolerance is the only knob that varies per round today.

### 3. Severity mapping

```
tolerance=low  → actionable: critical, high, medium, low  (everything)
tolerance=med  → actionable: critical, high, medium
tolerance=high → actionable: critical, high
```

Implemented as a threshold comparison on severity rank:

```python
SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
TOLERANCE_THRESHOLD = {"low": 0, "med": 1, "high": 2}
```

A finding is actionable if `SEVERITY_RANK[finding.severity] >= TOLERANCE_THRESHOLD[tolerance]`.

### 4. Acknowledgment protocol in worker instructions

The fix-retry worker's feedback prompt includes instructions:

```
For each finding below, you MUST either:
1. Fix it in code
2. Post a PR comment on the finding explaining why no change is needed

If this finding was flagged in a prior round and you already explained it,
add a code comment at the relevant location — two reviewers tripping on the
same pattern means future readers will too.
```

The worker is a Claude Code dispatch — it can run `gh pr comment` to post responses. The instructions are part of the feedback prompt, not a system prompt change.

### 5. Tracking acknowledged findings across rounds

The pipeline maintains a list of `AcknowledgedFinding` across rounds — findings that appeared in the actionable set but the worker did not fix (the file still has the same pattern after fix-retry). Detection is approximate: if a finding with the same `file` and similar `title` appears in both round N's actionable set and round N+1's findings, it's considered a repeat.

This list is passed to the worker in subsequent rounds as a "Prior Acknowledged Findings" section. The worker sees which findings have been flagged before and knows to escalate to a code comment.

**Matching rule:** Two findings match if they share the same `file` field AND either (a) the same `agent` field, or (b) one finding's `title` is a case-insensitive substring of the other's. This is simple enough to implement deterministically while catching rephrased versions of the same concern.

**Implementation:** After each fix-retry, diff the pre-fix actionable findings against the post-fix review findings using the matching rule above. Findings that persist are added to the acknowledged list.

### 6. Short-circuit on clean review

If a review round produces zero actionable findings (after tolerance filtering), the pipeline skips remaining rounds.

**Trade-off:** This assumes the cycle is ordered from strict to lenient (e.g., `low,med,high`). If an operator configures `high,low`, a clean round at `high` would short-circuit even though `low` might find lower-severity findings. This is accepted — the default ordering makes the assumption valid, and operators who configure unusual orderings understand the trade-off. The cycle is not validated for ordering, only for valid tolerance values.

### 7. CLI interface

```
--review-cycle TEXT  Comma-separated tolerance levels per review round.
                     Each level: low (all severities), med (medium+),
                     high (critical/high only). Default: low,med,high.
                     Example: --review-cycle high (single strict-only round).
```

Validation: each element must be one of `low`, `med`, `high`. Empty string or invalid values → error.

### 8. Verification review uses the last round's tolerance

After the final fix-retry succeeds, the verification review filters at the same tolerance as the last round in the cycle. This prevents the verification from surfacing findings that were intentionally below the tolerance threshold.

## Risks / Trade-offs

**[Worker may not follow acknowledgment protocol]** → The worker is instructed but not mechanically enforced. If it silently ignores a finding, the pipeline can't detect it. Mitigation: the PR comment with all findings provides human visibility. A future enhancement could parse PR comments to verify each finding was addressed.

**[Approximate repeat detection]** → Matching findings across rounds by file + title is fuzzy. A finding could be flagged as "new" when it's really the same concern rephrased. Mitigation: the worker uses judgment — if it recognizes a concern from prior feedback, it should escalate regardless of exact matching.

**[More review rounds = more cost]** → Default `[low, med, high]` is 3 rounds vs current 2. Mitigation: short-circuit on clean reviews means well-implemented changes exit early. Operators can use `--review-cycle high` for cost-sensitive runs.

**[Breaking change to strict-review-triage spec]** → The current spec says all findings trigger fix-retry. This change supersedes that with tolerance-based triage. The spec will be updated with a delta. Mitigation: the default cycle `[low, med, high]` starts with `low` (all severities), so the first round behaves identically to today.
