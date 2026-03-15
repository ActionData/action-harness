## 1. Update Result Model

- [ ] 1.1 In `models.py:OpenSpecReviewResult`: add `human_tasks_remaining: int = 0` field. This stores the count of `[HUMAN]` tasks that are incomplete.

## 2. Update OpenSpec Review Agent

- [ ] 2.1 In `openspec_reviewer.py:REVIEW_SYSTEM_PROMPT`: add instruction to recognize `[HUMAN]` tagged tasks. Add to the prompt: "When checking tasks.md, tasks containing `[HUMAN]` in the task text are expected to be agent-incomplete. Count them separately. If all non-HUMAN tasks are `[x]` and only HUMAN tasks remain `[ ]`, output `status: 'needs-human'` with `human_tasks_remaining` set to the count. Do NOT archive when status is `needs-human` — the change is not fully complete. Validation and semantic review still run normally."
- [ ] 2.2 In `openspec_reviewer.py:parse_review_result`: handle `status == "needs-human"`. Change the success check from `status == "approved"` to `status in ("approved", "needs-human")`. Extract `human_tasks_remaining` from the parsed JSON: `human_tasks_remaining=review_data.get("human_tasks_remaining", 0)`.

## 3. Pipeline Integration

- [ ] 3.1 In `models.py:RunManifest`: add `needs_human: bool = False` field.
- [ ] 3.2 In `pipeline.py:_run_openspec_review` (around line 736): after `parse_review_result`, check `review_result.human_tasks_remaining > 0`. If so: (a) post a PR comment via `gh pr comment` listing the remaining human tasks from `review_result.findings`, (b) add a `needs-human` label via `gh pr edit --add-label needs-human`. Both use `pr_result.pr_url` which is available as a parameter.
- [ ] 3.3 In `pipeline.py:_build_manifest`: add `needs_human: bool = False` parameter. Set from stages: check if any `OpenSpecReviewResult` in stages has `human_tasks_remaining > 0`. Set on the manifest. This follows the same pattern as cost_usd summing from stages.

## 4. Tests

- [ ] 4.1 In `tests/test_openspec_reviewer.py`: test `parse_review_result` with `status: "needs-human"`, `human_tasks_remaining: 3` — returns `success=True`, `human_tasks_remaining=3`.
- [ ] 4.2 In `tests/test_pipeline_review.py`: test pipeline with needs-human status — mock openspec reviewer to return needs-human. Assert pipeline exits successfully (exit code 0), `manifest.needs_human` is `True`, PR comment and label are posted.

## 5. Validation

```bash
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
```
