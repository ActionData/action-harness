## 1. Result Model

- [ ] 1.1 In `models.py`: define `OpenSpecReviewResult(StageResult)` with fields: `tasks_total` (int = 0), `tasks_complete` (int = 0), `validation_passed` (bool = False), `semantic_review_passed` (bool = False), `findings` (list[str] = []), `archived` (bool = False)

## 2. OpenSpec Reviewer Module

- [ ] 2.1 In `openspec_reviewer.py`: define `build_review_prompt(change_name)` that constructs the system prompt for the OpenSpec review agent. Include instructions to: read change specs and tasks, validate task completion, run `openspec validate <change_name>`, perform semantic review against the diff, archive with `openspec archive <change_name> -y` if structural checks pass, commit archive changes. The system prompt SHALL reference `Fission-AI/OpenSpec` on deepwiki for OpenSpec conventions. Include explicit instructions for the agent to output a final JSON block with keys: `status`, `tasks_total`, `tasks_complete`, `validation_passed`, `semantic_review_passed`, `findings`, `archived`.
- [ ] 2.2 In `openspec_reviewer.py`: define `dispatch_openspec_review(change_name, worktree_path, base_branch, max_turns, verbose)` that builds the CLI command and runs `claude` as subprocess in the worktree. Follow the `dispatch_worker` pattern from `worker.py`: build cmd list, run subprocess, capture output, track duration. Return raw output for parsing.
- [ ] 2.3 In `openspec_reviewer.py`: define `parse_review_result(raw_output, duration)` → `OpenSpecReviewResult` that extracts the JSON block from the worker's output `result` field. Classify as approved (`status == "approved"`) or findings. If JSON parsing fails, return `OpenSpecReviewResult(success=False, error="Failed to parse review output")`.
- [ ] 2.4 In `openspec_reviewer.py`: after the review agent completes, use `count_commits_ahead(worktree_path, base_branch)` to detect new archive commits. If new commits exist, run `git push origin HEAD` in the worktree. If push fails, return `OpenSpecReviewResult(success=False, error=push_stderr)`. Follow the subprocess pattern from `pr.py`.

## 3. Pipeline Integration

- [ ] 3.1 In `pipeline.py`: add OpenSpec review stage after `create_pr` succeeds. Call `dispatch_openspec_review` then `parse_review_result`. If the agent returns findings, log them to stderr and return `PrResult(success=False)`. If approved, the PR is ready for merge.
- [ ] 3.2 In `pipeline.py`: if the OpenSpec review succeeds and archive changes were pushed, add a comment on the PR via `gh pr comment` noting the archive was completed.

## 4. Tests

- [ ] 4.1 In `tests/test_openspec_reviewer.py`: test `build_review_prompt` includes change name, `openspec validate`, `openspec archive`, deepwiki reference, JSON output format instructions.
- [ ] 4.2 In `tests/test_openspec_reviewer.py`: test `dispatch_openspec_review` with mocked subprocess — verify claude CLI invocation args (system prompt, worktree cwd, output format).
- [ ] 4.3 In `tests/test_openspec_reviewer.py`: test `parse_review_result` — approved result (status=approved, archived=true), findings result (status=findings, archived=false with findings list), malformed JSON (returns error result).
- [ ] 4.4 In `tests/test_integration.py`: add `test_pipeline_with_openspec_review`. Mock `subprocess.run` to return success JSON for worker, mock eval to pass, mock PR creation to succeed, mock openspec reviewer to return approved result with archive commits. Assert pipeline returns success. Also test findings path: reviewer returns findings, pipeline returns failure.

## 5. Roadmap

- [ ] 5.1 In `openspec/ROADMAP.md`: add `openspec-review-agent` to the Bootstrap section after `agent-debuggability`.

## 6. Validation

```bash
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
```
