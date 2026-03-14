## Why

The harness currently creates PRs and runs an OpenSpec review agent, but has no code review capability. Every PR requires manual human review for bugs, test gaps, and quality issues. Review agents (bug-hunter, test-reviewer, quality-reviewer) already exist as Claude Code agent definitions and are used manually via the /ship skill. Embedding them into the pipeline closes the gap between "PR created" and "PR ready for merge," which is the prerequisite for auto-merge (roadmap item 4).

## What Changes

- Add a review-agents stage to the pipeline that runs after PR creation and before the OpenSpec review stage.
- Dispatch three independent Claude Code workers in parallel: bug-hunter, test-reviewer, and quality-reviewer. Each reads the PR diff via `gh pr diff` and produces structured findings.
- Introduce a `ReviewResult` model (per-agent) and a `ReviewSummary` model (aggregated) to capture findings with severity levels.
- Add a triage step that evaluates aggregated findings: if any high/critical findings exist, re-dispatch the code worker with findings as structured feedback, then re-run eval and re-create the PR before proceeding.
- Move the OpenSpec review stage to run after review agents complete (preserving its current behavior as the final gate).
- Add a review-agents section to the PR body summarizing findings from each reviewer.

## Capabilities

### New Capabilities
- `review-agents`: Parallel dispatch of code review agents (bug-hunter, test-reviewer, quality-reviewer) against a PR diff, structured finding collection, severity-based triage, and optional fix-retry loop.

### Modified Capabilities
<!-- No existing specs to modify -- openspec/specs/ is empty. The pipeline changes are all new capability. -->

## Impact

- **Code**: New module `src/action_harness/review_agents.py` for dispatch/parse/triage logic. Modifications to `pipeline.py` to insert the review-agents stage between PR creation and OpenSpec review. New models in `models.py`. Updates to `pr.py` to include review findings in the PR body.
- **Dependencies**: No new dependencies. Uses existing Claude Code CLI and `gh` CLI.
- **Pipeline flow change**: The stage order becomes: worktree -> worker -> eval -> PR -> review-agents (parallel) -> triage -> (optional fix retry) -> openspec-review -> done.
- **Cost**: Each pipeline run will dispatch up to 3 additional Claude Code workers for review. A fix-retry adds another worker + eval cycle.
