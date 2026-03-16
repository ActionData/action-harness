## Context

The fix-retry stage sends all actionable findings to the worker. With 3 review agents each producing 5-8 findings, the worker gets 15+ items. It addresses the easiest ones and leaves harder issues. Next round, it gets another 10-15 findings (remaining + new from fixes). This whack-a-mole pattern means findings accumulate instead of converging.

## Goals / Non-Goals

**Goals:**
- Cap findings sent per fix-retry (default 5)
- Prioritize by severity (critical > high > medium > low)
- Break ties by cross-agent agreement (findings flagged by multiple agents are higher priority)
- Remaining findings are deferred to the next review round, not lost
- Configurable via CLI flag

**Non-Goals:**
- Grouping findings by root cause (desirable but complex — defer)
- Changing how review agents produce findings (they still find everything)
- Changing the number of review rounds (that's review-tolerance/review-cycle)
- Changing the tolerance threshold logic (that filters by severity class, this caps by count)

## Decisions

### 1. Selection in `format_review_feedback`, not in the pipeline

The pipeline calls `format_review_feedback(results, tolerance, max_findings=N, ...)`. The function selects the top N findings by severity and formats them. The pipeline doesn't need to know the selection logic — it just passes the cap.

### 2. Priority scoring: severity + cross-agent count

Each finding gets a priority score using the existing `SEVERITY_RANK` dict from `review_agents.py`:
```python
# SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
priority = SEVERITY_RANK[finding.severity] * 10 + cross_agent_count
```

Where `cross_agent_count` is the number of distinct agents that flagged a finding on the same file with overlapping titles (case-insensitive substring match). This promotes findings that multiple agents independently identified — they're more likely to be real issues. The substring match is deliberately loose — it's a priority boost, not a gate. False positives in cross-agent counting slightly over-prioritize a finding but don't cause incorrect behavior.

Sorting by priority descending, take the top N.

### 3. Deferred findings logged to stderr, included in next round

Findings below the cap are NOT lost. They're:
- Logged to stderr: "[review] deferred N finding(s) below priority cap"
- Still present in the ReviewResult stages for the manifest
- Available to the next review round (they'll be re-flagged if still present)

The worker just doesn't get them as feedback for this retry.

### 4. Default cap of 5

Five findings is enough for one focused fix session. The worker can read 5 findings, understand the common thread, and address them systematically. Above 5, attention degrades.

**Alternative considered:** Dynamic cap based on finding severity (e.g., only 2 criticals, but 5 mediums). Rejected — adds complexity without clear benefit. Start simple, tune later.

### 5. Interaction with review-tolerance

`review-tolerance` filters findings by severity class (low/med/high tolerance). `focused-fix-retry` caps by count AFTER tolerance filtering. They compose cleanly:

```
All findings (15)
  → filter by tolerance (e.g., med: drop low → 10)
    → cap by max_findings (5)
      → sent to worker (5)
```

## Risks / Trade-offs

- [Important findings deferred] A critical finding at position 6 gets deferred → Mitigation: critical findings always rank higher than any non-critical finding due to severity scoring. A 6th critical finding means there are 5 worse issues to fix first.
- [More review rounds needed] Capping findings means more rounds to clear all issues → Mitigation: the review cycle already supports multiple rounds. Focused rounds converge faster than unfocused ones.
