## 1. Test Fixture Cleanup

- [x] 1.1 In `tests/test_worktree.py`: verify the existing `git_repo` fixture teardown (lines 13-63) actually cleans up all worktrees and temp dirs. If it works correctly, no changes needed. If worktrees leak despite the teardown, fix the teardown logic. Run `ls /tmp/action-harness-*/test-change 2>/dev/null | wc -l` before and after `uv run pytest tests/test_worktree.py` to verify.
- [x] 1.2 In `tests/test_integration.py`: convert `test_repo` fixture to a yield fixture with teardown that prunes git worktrees via `git worktree prune` and removes any `action-harness-*` temp dirs created during the test. Use the same pattern as `git_repo` in `test_worktree.py`. Also apply to `tests/test_pipeline_review.py` if it has a separate `test_repo` fixture.

## 2. Pipeline Success Cleanup

- [ ] 2.1 In `pipeline.py:_run_pipeline_inner`: after the `[pipeline] complete (success)` log (line 520) and before `return pr_result` (line 521), add: `if workspace_dir is None: cleanup_worktree(repo, worktree_path, branch)`. This cleans up temp-dir worktrees on success. Managed workspaces (`workspace_dir is not None`) are preserved — cleaned via `action-harness clean`.
- [ ] 2.2 Update the `cleanup_worktree` docstring in `worktree.py` (line 178): change "On PR creation: worktree is preserved (caller doesn't call this)" to "On success with temp dirs: cleaned up after all stages. Managed workspaces: preserved, cleaned via action-harness clean."

## 3. Validation

```bash
# Automated
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
uv run mypy src/

# Verify no leak
before=$(ls -d /tmp/action-harness-* 2>/dev/null | wc -l)
uv run pytest tests/test_worktree.py tests/test_integration.py -v
after=$(ls -d /tmp/action-harness-* 2>/dev/null | wc -l)
test "$after" -le "$before" && echo "OK: no leak" || echo "LEAKED: $((after - before)) dirs"
```
