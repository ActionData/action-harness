## 1. Test Fixture Cleanup

- [ ] 1.1 In `tests/test_worktree.py`: convert test methods that call `create_worktree` to use a helper that tracks created worktrees and cleans them up. Add a fixture or teardown that calls `cleanup_worktree` and removes the parent temp dir for each worktree created during the test.
- [ ] 1.2 In `tests/test_integration.py`: same pattern — ensure all worktrees created during pipeline tests are cleaned up. The test_repo fixture creates worktrees via `run_pipeline`; add teardown to prune worktrees and remove temp dirs.

## 2. Pipeline Success Cleanup

- [ ] 2.1 In `pipeline.py:_run_pipeline_inner`: after the final stage (openspec-review), if the pipeline succeeded and the worktree is a temp dir (not a managed workspace), call `cleanup_worktree(repo, worktree_path, branch, preserve_branch=True)`. Detect temp dir by checking if `workspace_dir` parameter was `None` (meaning tempfile was used).

## 3. Tests

- [ ] 3.1 Verify test suite doesn't leak: after running `uv run pytest -v`, check that no new `action-harness-*` dirs exist in `/tmp` (or the count doesn't increase).

## 4. Validation

```bash
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
```
