## Context

The harness creates PRs but doesn't currently merge them — human review is the gate. As `auto-merge` lands, the harness will control the full ship cycle. Without rollback infrastructure, a bad auto-merge requires manual git forensics to identify the right revert point.

Git tags are the right primitive: they're lightweight, they're already part of the git workflow, they travel with the repo, and they're queryable with standard git commands.

## Goals / Non-Goals

**Goals:**
- Tag main branch before merge as a rollback point (`harness/pre-merge/{label}`)
- Tag merge commit as a shipped feature marker (`harness/shipped/{label}`)
- `harness rollback` command to revert to a rollback point
- `harness history` command to list shipped features
- Tags pushed to remote so they're shared

**Non-Goals:**
- Automated rollback detection (monitoring for failures and auto-reverting) — future work
- Rollback of database migrations or external state — git-only
- Tag signing or verification
- Integration with release management tools (GitHub Releases, changelogs)

## Decisions

### 1. Tag naming convention

```
harness/pre-merge/{label}     — rollback point (tagged before merge)
harness/shipped/{label}       — feature marker (tagged after merge)
```

Where `{label}` is the change name (for `--change` runs) or the prompt slug (for `--prompt` runs). If a label would collide with an existing tag, append a timestamp suffix: `harness/shipped/{label}-{YYYYMMDD-HHMMSS}`.

**Alternative considered:** Semver-style tags (`v1.2.3`). Rejected — semver implies release management which is out of scope. The harness tags are operational markers, not release versions.

### 2. Pre-merge tag created immediately before PR creation

The `harness/pre-merge/{label}` tag is created on the base branch HEAD immediately before the PR is created. This captures the base state the harness worked against.

**Caveat:** The pre-merge tag captures the base branch HEAD at the time the harness creates the PR. If other work merges between PR creation and the harness PR merge, rolling back to this tag would also revert that unrelated work. This is an acceptable trade-off — the tag marks "the state the harness based its work on," not "the state just before merge."

**Alternative considered:** Tagging at merge time. Rejected — requires fetching the base branch HEAD just before merge, which is racy with concurrent merges and requires auto-merge integration that doesn't exist yet.

### 3. Post-merge tag via `harness tag-shipped` CLI command

Since auto-merge doesn't exist yet, the post-merge tag is created via a standalone CLI command: `harness tag-shipped --repo <path> --pr <url> --label <name>`. This command checks if the PR is merged via `gh pr view --json mergedAt,mergeCommitSha`, creates `harness/shipped/{label}` on the merge commit, and pushes the tag.

When `auto-merge` lands later, it can call `tag_shipped()` inline after merge confirmation. The CLI command remains available for manual use.

**Alternative considered:** Polling for merge status from within the pipeline. Rejected — the pipeline exits after PR creation, and polling adds complexity. A manual command is simpler and sufficient for now.

### 4. Rollback creates a single revert commit via tree-level diff

`harness rollback` creates a single commit that sets the working tree to match the tagged state. Implementation: `git read-tree -m -u {tag}` to update the index and working tree to match the tag, then `git commit -m "Rollback to {tag}"`. This produces one clean commit regardless of intermediate merge commits or conflict-prone history.

It does NOT force-push, reset, or rewrite history. The rollback is a forward-moving commit that preserves the full history.

**Prerequisite:** The working tree must be clean (no uncommitted changes). The command checks for this and exits with an error if dirty.

**Alternative considered:** `git revert --no-commit {tag}..HEAD`. Rejected — fails on merge commits (requires `-m 1`), can produce conflicts on intermediate commits, and doesn't guarantee a single clean commit. Tree-level reset is simpler and conflict-free.

**Alternative considered:** `git reset --hard` to the tag. Rejected — destructive, rewrites shared history, loses the record of what was rolled back.

### 5. Tags pushed to remote individually

After creating a tag, the harness pushes it individually with `git push origin <tag_name>` rather than `--tags` (which would push all local tags, potentially including unrelated ones). Tags are only useful for rollback if they exist on the remote.

## Risks / Trade-offs

- [Tag pollution] Many tags could accumulate over time → Mitigation: tags are namespaced under `harness/` and can be pruned with `git tag -d` or a future `harness clean-tags` command.
- [Concurrent merges] Other work may merge between the pre-merge tag and the actual merge, making the tag not a clean rollback point → Mitigation: the pre-merge tag captures the harness's known-good state. Rolling back to it is still valid — it's just that other work merged in between would also be reverted. Document this.
- [No auto-merge yet] Post-merge tagging depends on knowing when a PR is merged. Without auto-merge, this requires polling or a webhook → Mitigation: start with manual `harness tag-shipped` or poll via `gh pr view`. Auto-merge integration comes later.
