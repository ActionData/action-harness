## Why

As the harness gains autonomy — auto-merge, always-on operation, multi-task execution — the blast radius of a bad change increases. If the harness ships a broken feature, there's currently no structured way to identify what state was known-good and roll back to it.

Git tags provide a lightweight, native mechanism for marking rollback points. By tagging the main branch before each harness-shipped merge, the operator (or the harness itself) can quickly identify and revert to the last known-good state. As a bonus, the tags create a human-readable changelog of harness-shipped features directly in the git history.

## What Changes

- The harness tags the main branch with `harness/pre-merge/{change-or-slug}` before merging a PR, creating a rollback point
- After a successful merge, the harness tags the merge commit with `harness/shipped/{change-or-slug}` to mark the feature delivery
- New CLI command: `harness rollback --repo <path> [--to <tag>]` that reverts main to the specified (or most recent) pre-merge tag
- `harness history --repo <path>` lists harness-shipped tags with timestamps and change names

## Capabilities

### New Capabilities
- `rollback-tags`: Git tag management for rollback points and shipped feature markers. Includes pre-merge tagging, post-merge tagging, rollback command, and history listing.

### Modified Capabilities
None

## Impact

- `pipeline.py` — add pre-merge tagging before PR merge, post-merge tagging after successful merge
- `cli.py` — new `rollback` and `history` commands
- Git tags namespace: `harness/pre-merge/*` and `harness/shipped/*`
- Requires `auto-merge` or manual merge workflow to trigger post-merge tagging
- Tags must be pushed to remote (`git push --tags`)
