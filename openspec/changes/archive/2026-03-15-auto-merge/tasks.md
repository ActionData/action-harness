## 1. MergeResult Model [no dependencies]

- [x] 1.1 Add `MergeResult(StageResult)` to `models.py` with `stage: Literal["merge"] = "merge"`, `merged: bool = False`, `merge_blocked_reason: str | None = None`, `ci_passed: bool | None = None`. Add `MergeResult` to the `StageResultUnion` discriminated union (add it to the union type on the same line as the other stage types).
- [x] 1.2 Add tests: `MergeResult` construction (success with `merged=True`, blocked with `merged=False` and `merge_blocked_reason` set, failed with `success=False`). Roundtrip through `RunManifest.stages` via `model_dump_json()` / `model_validate_json()` — assert `type(stages[-1]) is MergeResult`, `stages[-1].merged == True`, `stages[-1].merge_blocked_reason is None`.

## 2. Merge Logic [depends: 1]

- [x] 2.1 Create `src/action_harness/merge.py` with `merge_pr(pr_url: str, worktree_path: Path, delete_branch: bool = True, verbose: bool = False) -> MergeResult`. Runs `gh pr merge <url> --merge --delete-branch` via subprocess. Returns `MergeResult(success=True, merged=True)` on success, `MergeResult(success=False, merged=False, error=...)` on failure. Log outcome to stderr via `typer.echo(..., err=True)`.
- [x] 2.2 Add `check_merge_gates(protected_files: list[str], findings_remain: bool, openspec_review_passed: bool, skip_review: bool) -> tuple[dict[str, bool], bool]`. Evaluates ALL gates (no short-circuit) and returns `(gates_dict, all_passed)` where `gates_dict` maps gate names to pass/fail: `{"no_protected_files": bool, "review_clean": bool, "openspec_review_passed": bool}`. `review_clean` is True when `findings_remain is False` OR `skip_review is True`.
- [x] 2.3 Add `wait_for_ci(pr_url: str, worktree_path: Path, timeout_seconds: int = 600, verbose: bool = False) -> bool`. Runs `gh pr checks <url> --watch --fail-fast` with timeout via subprocess. Returns True if all checks pass, False on failure or timeout. Log outcome to stderr.
- [x] 2.4 Add `post_merge_blocked_comment(pr_url: str, worktree_path: Path, gates: dict[str, bool], verbose: bool = False) -> None`. Posts a PR comment with a checklist showing each gate as `[x]` (passed) or `[ ]` (failed), with descriptive labels. Best-effort — log warning on failure, never raise.
- [x] 2.5 Add tests: `merge_pr` success/failure (mock `gh`). `check_merge_gates` — all pass returns `({all True}, True)`, protected files blocks (returns False for `no_protected_files`), findings remain blocks (returns False for `review_clean`), openspec fails blocks, `skip_review=True` makes `review_clean` True regardless of `findings_remain`, all gates evaluated even when first fails (verify dict has all 3 keys). `wait_for_ci` pass/fail/timeout (mock subprocess with timeout). `post_merge_blocked_comment` posts correct body (mock `gh pr comment`).

## 3. CLI Flag [depends: 1]

- [x] 3.1 Add `--auto-merge` flag (bool, default False) and `--wait-for-ci` flag (bool, default False) to the `run` command in `cli.py`. If `--wait-for-ci` is provided without `--auto-merge`, exit with error "`--wait-for-ci` requires `--auto-merge`". Pass both through to `run_pipeline()`.
- [x] 3.2 Update `--dry-run` output to show `auto-merge: enabled/disabled` and `wait-for-ci: enabled/disabled`.
- [x] 3.3 Update `run()` docstring and help text to document the new flags.
- [x] 3.4 Add CLI tests: `--help` includes auto-merge and wait-for-ci, `--dry-run` with `--auto-merge` shows the flag, `--wait-for-ci` without `--auto-merge` exits with error.

## 4. Pipeline Integration [depends: 2, 3]

- [x] 4.1 Add `auto_merge: bool = False` and `wait_for_ci: bool = False` parameters to `run_pipeline()` and `_run_pipeline_inner()`.
- [x] 4.2 Before the review block in `_run_pipeline_inner()`, initialize `findings_remain = False` so it's always defined regardless of whether `skip_review` is True.
- [x] 4.3 After the openspec-review stage, just before the `[pipeline] complete (success)` log line and `return pr_result`: if `auto_merge` is True, compute `openspec_review_passed = review_result is None or review_result.success`. Call `check_merge_gates(protected_files, findings_remain, openspec_review_passed, skip_review)` to get `(gates, all_passed)`. If `all_passed` and `wait_for_ci` is True, call `wait_for_ci()` and set `ci_passed`. If `all_passed` (and CI passed if requested), call `merge_pr()`. If blocked, call `post_merge_blocked_comment(pr_result.pr_url, worktree_path, gates)`. Append `MergeResult` to stages in all cases. The pipeline still returns `pr_result` — merge outcome is advisory, not a pipeline gate.
- [x] 4.4 Add pipeline tests: auto-merge enabled + all gates pass → `MergeResult(merged=True)` in stages. Auto-merge + protected files → `MergeResult(merged=False, merge_blocked_reason=...)` + comment posted. Auto-merge + findings remain → blocked. Auto-merge disabled → no `MergeResult` in stages. Auto-merge + `wait_for_ci` pass → merged. Auto-merge + CI fail → blocked. Auto-merge + `skip_review` + no openspec review (prompt mode) → gates pass.

## 5. Logging [depends: 4]

- [x] 5.1 Log merge decisions to stderr: "auto-merge: all gates passed, merging PR" or "auto-merge blocked: {reason}". Log `gh pr merge` outcome.
- [x] 5.2 Add merge event to event logger: `merge.completed` with `gates`, `merged`, `blocked_reason`, `ci_passed`.

## 6. Validation [depends: all]

- [x] 6.1 Run full test suite (`uv run pytest -v`) and verify no regressions
- [x] 6.2 Run lint and type checks (`uv run ruff check .` and `uv run mypy src/`)
- [x] 6.3 Run `harness run --change <change> --repo . --auto-merge --dry-run` and verify output shows `auto-merge: enabled`
