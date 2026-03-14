## Why

The harness can now implement changes, run eval, dispatch review agents, fix findings, and open PRs autonomously. The next step toward auto-merge is ensuring that changes to load-bearing code — the eval runner, core dispatch logic, safety mechanisms — always require human review. Without protected paths, auto-merge would allow the harness to modify its own safety mechanisms and merge without oversight.

Protected paths are the prerequisite for auto-merge. They define which files/patterns always escalate to human review, regardless of what review agents say.

## What Changes

- Add a `.harness/protected-paths.yml` config file convention for declaring protected file patterns
- The pipeline checks the diff against protected patterns after PR creation
- If protected files are modified, the pipeline flags the PR for human review (skips auto-merge when it exists, adds a label/comment now)
- Protected paths are glob patterns (e.g., `src/action_harness/pipeline.py`, `src/action_harness/evaluator.py`, `*.md`)
- Default protected paths for the harness itself: pipeline.py, evaluator.py, worktree.py, models.py, cli.py

## Capabilities

### New Capabilities

- `protected-paths`: Configuration-driven file protection that flags PRs modifying sensitive files for human review. Reads patterns from `.harness/protected-paths.yml`, checks the diff, and annotates the PR accordingly.

### Modified Capabilities

## Impact

- New config file convention: `.harness/protected-paths.yml`
- New module: `src/action_harness/protection.py` — pattern matching and diff checking
- Modified: `src/action_harness/pipeline.py` — check protected paths after PR creation
- Modified: `src/action_harness/models.py` — add protection check result to manifest
- Default config for this repo: `.harness/protected-paths.yml` with harness core files
