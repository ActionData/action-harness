## Context

`run_eval` runs all eval commands and fails on the first non-zero exit code. It doesn't know whether the failure existed before the worker's changes.

## Goals / Non-Goals

**Goals:**
- Know which eval commands pass/fail before the worker starts
- Only flag regressions (commands that were passing but now fail)
- Pre-existing failures noted in manifest but don't block

**Non-Goals:**
- Fixing pre-existing issues automatically
- Scoping lint to changed files only (future optimization)

## Decisions

### 1. Run baseline eval in the worktree before worker dispatch

Run all eval commands in the freshly created worktree (which is identical to the base branch). Record which commands pass and which fail.

**Why:** The worktree is the clean baseline. Running eval there before the worker touches anything gives us ground truth.

### 2. Post-worker eval compares against baseline

After the worker completes, run eval again. For each command:
- Was passing, still passing → OK
- Was passing, now failing → REGRESSION (fail the eval)
- Was failing, still failing → PRE-EXISTING (note, don't block)
- Was failing, now passing → FIXED (the worker fixed a pre-existing issue, bonus)

**Why:** Only regressions matter. Pre-existing failures are the repo's problem, not the worker's.

### 3. Store baseline results in the manifest

Add `baseline_eval` to the manifest with per-command pass/fail status. This gives full visibility into what was already broken.

**Why:** Operators need to know the repo's health independent of the worker's changes.

## Risks / Trade-offs

**[Risk] Baseline eval doubles the eval time.**
→ Mitigation: Eval commands are typically fast (seconds). The time saved on retry rounds (no fixing pre-existing issues) more than compensates.

**[Trade-off] Worker doesn't get to fix pre-existing issues.**
→ Acceptable. Fixing pre-existing issues is a separate task, not part of the current change.
