Prerequisites: implement after `enrich-pr-description` (which modifies `create_pr` signature in `pipeline.py`).

## 1. Result Model

- [x] 1.1 In `models.py`: define `OpenSpecReviewResult(StageResult)` with fields: `tasks_total` (int = 0), `tasks_complete` (int = 0), `validation_passed` (bool = False), `semantic_review_passed` (bool = False), `findings` (list[str] = []), `archived` (bool = False)

## 2. OpenSpec Reviewer Module

- [x] 2.1 In `openspec_reviewer.py`: define the system prompt text as a constant `REVIEW_SYSTEM_PROMPT` with a `{change_name}` placeholder. The prompt SHALL instruct the agent to: (1) read `openspec/changes/{change_name}/tasks.md` and verify all tasks are `[x]`, (2) run `openspec validate {change_name}` and check for errors, (3) read the change's specs and compare against the diff for semantic alignment (advisory, not blocking), (4) if structural checks pass (tasks complete + validation clean), run `openspec archive {change_name} -y` and commit the results, (5) output a final JSON block with keys: `status`, `tasks_total`, `tasks_complete`, `validation_passed`, `semantic_review_passed`, `findings`, `archived`. Reference `Fission-AI/OpenSpec` on deepwiki for OpenSpec conventions.
- [x] 2.2 In `openspec_reviewer.py`: define `build_review_prompt(change_name) -> str` that interpolates `change_name` into `REVIEW_SYSTEM_PROMPT`.
- [x] 2.3 In `openspec_reviewer.py`: define `dispatch_openspec_review(change_name, worktree_path, base_branch, max_turns, permission_mode, verbose)` that builds the CLI command and runs `claude` as subprocess in the worktree. Always include `--permission-mode <permission_mode>` (default `bypassPermissions` for headless operation). Follow the `dispatch_worker` pattern from `worker.py`: build cmd list, run subprocess, capture output, track duration. Return raw output and duration for parsing.
- [x] 2.4 In `openspec_reviewer.py`: define `parse_review_result(raw_output, duration) -> OpenSpecReviewResult` that extracts the JSON block from the worker's output `result` field. Classify as approved (`status == "approved"`) or findings. If JSON parsing fails, return `OpenSpecReviewResult(success=False, error="Failed to parse review output")`.
- [x] 2.5 In `openspec_reviewer.py`: after dispatch completes, use `count_commits_ahead(worktree_path, base_branch)` from `worker.py` to detect new archive commits. If new commits exist, run `git push origin HEAD` in the worktree. If push fails, return `OpenSpecReviewResult(success=False, error=push_stderr)`. Follow the subprocess pattern from `pr.py`.

## 3. Pipeline Integration

- [x] 3.1 In `pipeline.py`: add OpenSpec review stage after `create_pr` succeeds. Call `dispatch_openspec_review` (passing `permission_mode` from pipeline params) then `parse_review_result`. If the agent returns findings, log them to stderr and return `PrResult(success=False)`. If approved, the PR is ready for merge.
- [x] 3.2 In `pipeline.py`: if the OpenSpec review succeeds and archive changes were pushed, add a comment on the PR via `gh pr comment` noting the archive was completed.

## 4. Tests

- [x] 4.1 In `tests/test_openspec_reviewer.py`: test `build_review_prompt` includes change name, `openspec validate`, `openspec archive`, deepwiki reference, JSON output format instructions.
- [x] 4.2 In `tests/test_openspec_reviewer.py`: test `dispatch_openspec_review` with mocked subprocess — verify claude CLI invocation args (system prompt, worktree cwd, output format, `--permission-mode bypassPermissions`).
- [x] 4.3 In `tests/test_openspec_reviewer.py`: test `parse_review_result` — approved result (status=approved, archived=true), findings result (status=findings, archived=false with findings list), malformed JSON (returns error result with "Failed to parse" message).
- [x] 4.4 In `tests/test_integration.py`: add `test_pipeline_with_openspec_review`. Mock `subprocess.run` to return success JSON for worker, mock eval to pass, mock PR creation to succeed, mock openspec reviewer to return approved result with archive commits. Assert pipeline returns success. Also test findings path: reviewer returns findings, pipeline returns failure.

## 5. Roadmap

- [x] 5.1 In `openspec/ROADMAP.md`: add `openspec-review-agent` to the Bootstrap section (already done in this proposal PR).

## 6. Validation

```bash
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
```
