## 1. Enrich _build_pr_body

- [ ] 1.1 In `pr.py`: add `_read_proposal_why(worktree_path, change_name)` helper that reads `openspec/changes/<name>/proposal.md` from the worktree. Extract text between the `## Why` heading and the next `##`-level heading (or end of file). Strip leading/trailing whitespace. Returns `None` if file missing or section not found.
- [ ] 1.2 In `pr.py`: add `_get_diff_stat(worktree_path, base_branch)` helper that runs `git diff --stat origin/<base_branch>..HEAD` in the worktree and returns the output. Use `origin/<base_branch>` because worktrees may not have a local ref for the base branch. If output exceeds 30 lines, truncate and append `\n... (truncated)`.
- [ ] 1.3 In `pr.py`: add `_get_commit_log(worktree_path, base_branch)` helper that runs `git log --oneline origin/<base_branch>..HEAD` in the worktree and returns the output. If empty, return `None`.
- [ ] 1.4 In `pr.py`: update `_build_pr_body` signature to accept `worktree_path: Path`, `base_branch: str`, and `worker_result: WorkerResult` in addition to existing params. Build the body with sections: Background (from proposal, omit if None), Changes (diff stat), Commits (log, omit if None), Worker (cost from `worker_result.cost_usd` if not None, duration from `worker_result.duration_seconds` if not None, observations from `worker_result.worker_output` truncated to 500 chars with `... (truncated)` if longer), Eval Results (existing), and footer.
- [ ] 1.5 In `pr.py`: update `create_pr` signature to accept `worker_result: WorkerResult` and `base_branch: str`. Pass them through to `_build_pr_body` along with `worktree_path`.

## 2. Update pipeline wiring

- [ ] 2.1 In `pipeline.py`: extract `base_branch = _get_worktree_base(repo)` before the retry loop and store as a local variable. Pass both `worker_result` and `base_branch` to the `create_pr` call. Update `create_pr` call to match new signature.

## 3. Tests

- [ ] 3.1 In `tests/test_pr.py`: add tests for `_read_proposal_why` — file exists with Why section (returns content between `## Why` and next `##`), file missing (returns None), file without Why section (returns None).
- [ ] 3.2 In `tests/test_pr.py`: update `_build_pr_body` tests to verify new sections. Mock git subprocess calls for diff stat and commit log. Test: Background section present when proposal exists, Changes section with diff stat, Commits section with log, Worker section with cost/duration/observations. Test truncation: diff stat >30 lines truncated with indicator, observations >500 chars truncated with indicator.
- [ ] 3.3 In `tests/test_pr.py`: update `create_pr` tests for new signature — pass `worker_result: WorkerResult` and `base_branch: str`.
- [ ] 3.4 In `tests/test_integration.py`: update integration tests to pass `worker_result` and `base_branch` to `create_pr` if signature changed.

## 4. Validation

```bash
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
```
