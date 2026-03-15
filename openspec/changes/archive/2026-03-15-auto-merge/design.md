## Context

The pipeline currently flows: worktree → worker → eval → PR → protected-paths check → review agents → openspec-review → "complete (success)". The PR sits open for a human to merge. Auto-merge adds a final stage that merges the PR when all gates pass.

## Goals / Non-Goals

**Goals:**
- `--auto-merge` flag on `harness run` (opt-in, default off)
- Merge PR via `gh pr merge --merge` when all gates pass
- Block merge when protected files are touched (defer to human)
- Block merge when review findings remain after fix-retry rounds
- Block merge when OpenSpec review fails
- Optionally wait for CI status checks before merging
- Log merge decisions and outcomes

**Non-Goals:**
- Squash or rebase merge strategies (use merge commits for now)
- Auto-merge when CI is failing (CI must pass or not be configured)
- Branch deletion after merge (gh pr merge --delete-branch handles this)
- Webhook-based merge monitoring (that's `always-on`)
- Merge approval by external reviewers (the harness is the reviewer)

## Decisions

### 1. Opt-in via --auto-merge flag

Auto-merge is off by default. The operator must explicitly enable it with `--auto-merge`. This prevents accidental autonomous merges during early adoption and lets operators build trust incrementally.

**Alternative considered:** Always-on auto-merge with `--no-auto-merge` to disable. Rejected — merging is a destructive action that changes shared state. Opt-in is safer.

### 2. Merge via `gh pr merge --merge --delete-branch`

Use the GitHub CLI to merge. This handles all GitHub-specific logic (merge commit creation, branch deletion, status checks). The harness doesn't need to implement merge mechanics — it delegates to `gh`.

### 3. All gates evaluated (no short-circuit) for full checklist

All three gates are always evaluated — even when one fails — so the blocked comment can show a complete checklist. The function returns a `dict[str, bool]` mapping gate names to pass/fail, plus the overall result.

```
Gate 1: "no_protected_files"
  → protected_files list from protection check must be empty

Gate 2: "review_clean"
  → After all review rounds + fix-retries, findings_remain must be False
  → OR skip_review was set (operator explicitly skipped review)

Gate 3: "openspec_review_passed"
  → review_result.success must be True or review_result is None (skipped)
```

If ANY gate fails, the PR stays open with a comment showing all gates' status.

### 4. CI wait via `gh pr checks --watch`

Before merging, optionally wait for CI status checks to pass. Use `gh pr checks <url> --watch --fail-fast` with a timeout. If CI fails or times out, block the merge.

This is opt-in within auto-merge: `--auto-merge --wait-for-ci`. Without `--wait-for-ci`, the harness merges immediately after its own gates pass (CI may still be running). The rationale: the harness already ran eval locally, so CI is a secondary confirmation.

**Alternative considered:** Always waiting for CI. Rejected — many repos don't have CI, and waiting adds latency. Operators who want CI gating can enable it.

### 5. Merge blocked comment

When auto-merge is enabled but blocked, the harness posts a PR comment explaining why:

```
## Auto-merge blocked

- [x] Eval passed
- [ ] No protected files touched (BLOCKED: CLAUDE.md, pyproject.toml)
- [x] Review agents clean
- [x] OpenSpec review passed

This PR requires human review due to protected file changes.
```

This gives the human reviewer immediate context about what passed and what didn't.

### 6. New stage model: `MergeResult`

A new `MergeResult(StageResult)` with `stage: Literal["merge"]` and fields for `merged: bool`, `merge_blocked_reason: str | None`, `ci_passed: bool | None`. Added to the `StageResultUnion` discriminator.

### 7. Pipeline success semantics

The pipeline returns `PrResult` which drives `manifest.success`. When auto-merge is enabled:
- **Merge succeeds:** pipeline returns `pr_result` with `success=True` (the PR was created AND merged)
- **Merge blocked by gate:** pipeline returns `pr_result` with `success=True` (the PR was created; the block is advisory, not a failure). The `MergeResult` in stages records `merged=False`.
- **Merge command fails** (`gh pr merge` non-zero): pipeline returns `pr_result` with `success=True` (the PR was created). The `MergeResult` records `success=False, merged=False, error=...`. This is NOT a pipeline failure — the PR is still open for manual merge.

**Rationale:** The pipeline's job is to produce a reviewable PR. Auto-merge is a convenience, not a gate. A failed merge doesn't invalidate the PR.

### 8. `--wait-for-ci` requires `--auto-merge`

If `--wait-for-ci` is provided without `--auto-merge`, the CLI exits with an error: "`--wait-for-ci` requires `--auto-merge`". CI wait has no effect without merge intent.

## Risks / Trade-offs

- [Accidental merge] Auto-merge could merge bad code if gates have gaps → Mitigation: opt-in flag, protected paths as hard block, eval + review agents as quality gates
- [CI race] Merging before CI completes could merge code that CI would reject → Mitigation: `--wait-for-ci` flag, or rely on branch protection rules configured in GitHub
- [Protected paths false negative] If `.harness/protected-paths.yml` is missing, no files are protected → Mitigation: document this. The absence of a config file means the operator hasn't configured protection.
- [gh CLI dependency] Merge requires `gh` CLI authenticated with merge permissions → Mitigation: already validated at pipeline start. Merge failure is non-fatal (PR stays open).
