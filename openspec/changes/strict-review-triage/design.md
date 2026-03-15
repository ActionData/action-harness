## Context

The `triage_findings` function (review_agents.py:317) currently returns `True` only when a finding has severity `critical` or `high`. The pipeline (pipeline.py:434) only calls `_run_review_fix_retry` when `triage_findings` returns `True`. Medium and low findings are posted as a PR comment and never addressed.

The `format_review_feedback` function (review_agents.py:330) only includes high/critical findings in the feedback string sent to the fix-retry worker. Even if triage triggered on medium findings, the worker wouldn't see them.

## Goals / Non-Goals

**Goals:**
- Worker addresses ALL findings by default
- Only skip findings that are factually wrong or style opinions not grounded in repo rules
- Quality reviewer grounds findings in the repo's conventions (CLAUDE.md, linter config, existing patterns)
- Multiple fix-retry rounds allowed to address all findings

**Non-Goals:**
- Automated classification of "factually wrong" (the worker decides this — it can explain why a finding is wrong in its commit message)
- Changing the review agent dispatch or output format
- Adding new review agents

## Decisions

### 1. `triage_findings` triggers on any findings

Change `triage_findings` to return `True` if there are ANY findings (regardless of severity). The current severity-based filtering is removed. The worker gets all findings and addresses them.

**Why:** Severity indicates urgency, not whether to fix. A medium finding is still a real issue. The worker should treat review like a good engineer — address everything.

### 2. `format_review_feedback` includes all findings

Update to include all findings in the feedback string, not just high/critical. Group by agent, include severity/file/line/description for each.

**Why:** The worker needs to see all findings to address them. Filtering the feedback is what caused findings to be ignored.

### 3. Quality reviewer prompt reads CLAUDE.md and cites rules

Update the quality-reviewer system prompt to explicitly instruct: read CLAUDE.md first, check linter config (pyproject.toml ruff/mypy sections), observe existing patterns. Every finding must cite the rule or convention it's based on. Findings not grounded in repo rules should not be raised.

**Why:** Generic style opinions create noise. The reviewer should enforce the repo's standards, not its own preferences.

### 4. Cap fix-retry rounds at 2

Allow up to 2 fix-retry rounds (currently 1). If findings remain after 2 rounds, the pipeline posts them as a comment and continues — the worker had its chance.

**Why:** Infinite retry loops are wasteful. 2 rounds is enough for the worker to address all findings. Remaining issues after 2 rounds likely need human judgment.

## Risks / Trade-offs

**[Risk] More fix-retry rounds increase cost.**
→ Mitigation: Most runs will need 0-1 rounds. The cap at 2 bounds cost. The alternative — shipping known issues — is worse.

**[Trade-off] Worker may disagree with a finding.**
→ The worker can explain why a finding is wrong in its commit message. The PR comment still shows the original finding for human review.
