## Why

The review agent triage currently only triggers a fix-retry for high/critical severity findings. Medium and low findings are posted as a PR comment and ignored. This means the harness ships PRs with known issues it identified but didn't address.

The harness should treat review findings the way a good engineer treats code review: address everything. The only acceptable reasons to skip a finding are:
1. The finding is objectively wrong (factual error in the reviewer's analysis)
2. The suggestion is purely a style opinion not grounded in the repo's established rules

Everything else gets fixed.

Additionally, the quality reviewer should ground its reviews in the repo's actual conventions — CLAUDE.md rules, linter config, existing patterns — not generic opinions. A finding that contradicts the repo's established style is the reviewer's bug, not the code's bug.

## What Changes

- Change triage logic: the worker addresses ALL findings by default
- The only skip conditions are: factually incorrect finding, or style opinion not backed by repo rules
- The fix-retry feedback includes all findings, not just high/critical
- The quality-reviewer system prompt is updated to read and follow the repo's CLAUDE.md, linter config, and existing conventions — findings must cite the rule they're enforcing
- The triage function becomes simpler: everything is actionable unless explicitly excluded
- Multiple fix-retry rounds if needed (currently capped at 1) to address all findings

## Capabilities

### New Capabilities

- `strict-review-triage`: Worker addresses all review findings. Skip only for factually wrong findings or style opinions not grounded in repo rules. Quality reviewer anchored to repo conventions.

### Modified Capabilities

## Impact

- `src/action_harness/review_agents.py` — update `triage_findings` to return all actionable findings, update quality-reviewer prompt to cite repo rules
- `src/action_harness/pipeline.py` — trigger fix-retry on any actionable findings (not just high/critical)
- Review agent system prompts — quality reviewer reads CLAUDE.md and linter config, cites rules in findings
- `tests/test_review_agents.py` — update triage tests
- `tests/test_pipeline_review.py` — update integration tests
