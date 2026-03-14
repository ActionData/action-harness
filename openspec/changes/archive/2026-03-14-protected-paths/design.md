## Context

The harness pipeline currently: worktree → worker → eval → PR → review-agents → fix-retry → openspec-review. All PRs are opened for human review. When auto-merge is added (roadmap #4), PRs that pass all checks will be merged automatically. Protected paths ensure that changes to critical files always require human review, even with auto-merge enabled.

For now (before auto-merge), protected paths add a label and comment to the PR indicating human review is required. This is informational — the harness doesn't block, it flags.

## Goals / Non-Goals

**Goals:**
- Declare protected file patterns in a repo-level config file
- Check the PR diff against protected patterns
- Flag PRs that touch protected files (label + comment)
- Include protection status in the run manifest
- Ship with default protected paths for the harness's own repo

**Non-Goals:**
- Blocking PR creation (the PR is still created, just flagged)
- Auto-merge integration (that's a separate change that reads the protection flag)
- Per-branch or per-change-type rules (all changes are equal for now)
- Directory-level protection (patterns match files, not directories)

## Decisions

### 1. Config file at `.harness/protected-paths.yml`

Store protected path patterns in `.harness/protected-paths.yml` in the target repo. YAML format with a simple list of glob patterns:

```yaml
protected:
  - "src/action_harness/pipeline.py"
  - "src/action_harness/evaluator.py"
  - "src/action_harness/worktree.py"
  - "src/action_harness/models.py"
  - "src/action_harness/cli.py"
  - "CLAUDE.md"
```

**Why:** YAML is consistent with other config conventions. `.harness/` directory keeps harness config separate from application code. Glob patterns are familiar and flexible.

### 2. Check diff via `git diff --name-only` in the worktree

Run `git diff --name-only origin/<base>..HEAD` in the worktree to get the list of changed files, then match against protected patterns using `fnmatch`.

**Why:** Simple, deterministic, no GitHub API needed. Uses the same git commands the pipeline already uses for diff stat and commit log.

### 3. Flag with PR comment and label, don't block

When protected files are detected, post a PR comment listing the protected files and add a `protected-paths` label via `gh pr edit --add-label`. The pipeline continues — it doesn't fail or skip stages.

**Why:** Before auto-merge exists, blocking would add friction without value (humans review all PRs anyway). The flag is informational, positioning for auto-merge to read it later.

### 4. Protection check runs after PR creation, before review agents

The check happens early — after the PR exists (so we can comment/label) but before review agents run. This way review agents can see the protection flag in their context.

**Why:** Review agents benefit from knowing which files are protected — they can pay extra attention to those files.

### 5. Include protection result in manifest

Add a `protected_files: list[str]` field to `RunManifest` listing any protected files that were modified. Empty list means no protected files were touched.

**Why:** The manifest is the canonical record. Auto-merge will read this field to decide whether to merge or escalate.

### 6. Missing config file means no protection

If `.harness/protected-paths.yml` doesn't exist in the repo, treat all files as unprotected. Log a note to stderr.

**Why:** Protection is opt-in. Repos that don't declare protected paths get the default behavior (human reviews everything anyway).

## Risks / Trade-offs

**[Risk] Glob patterns are too coarse for some repos.**
→ Mitigation: Start with file-level patterns. Directory patterns (`src/action_harness/*.py`) and negative patterns (`!tests/`) can be added later.

**[Trade-off] No enforcement until auto-merge exists.**
→ Acceptable. The flag is the prerequisite. Auto-merge reads the flag.
