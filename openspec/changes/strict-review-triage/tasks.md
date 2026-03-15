## 1. Update Triage and Feedback Logic

- [ ] 1.1 In `review_agents.py:triage_findings`: change to return `True` if any findings exist (remove the severity filter). The function becomes: `return any(r.findings for r in results)`.
- [ ] 1.2 In `review_agents.py:format_review_feedback`: remove the severity filter — include ALL findings in the feedback string. Group by agent with severity/file/line/description for each. Update the footer text from "Fix the high/critical issues above" to "Fix the issues above and re-run eval to verify." Update the corresponding test assertion in `test_review_agents.py:test_contains_footer`.

## 2. Update Quality Reviewer Prompt

- [ ] 2.1 In `review_agents.py`: update the quality-reviewer system prompt. Add to the prompt text: "Before reviewing, read the repo's CLAUDE.md (if it exists) and check linter configuration in pyproject.toml or equivalent. Ground every finding in a specific rule from these files or an observable existing pattern in the codebase. Do not raise findings based on personal preference — cite the rule you are enforcing."

## 3. Pipeline Review-Fix Loop

- [ ] 3.1 In `pipeline.py:_run_pipeline_inner`: replace the single `needs_fix` / `_run_review_fix_retry` call block (around the Stage 5 section) with a loop: `for review_round in range(2)` that (a) calls `_run_review_agents`, (b) checks `triage_findings`, (c) if needs fix, calls `_run_review_fix_retry`, (d) if no findings, breaks. After the loop exits, if findings remain (triage still True after 2 rounds), call `_post_review_comment` with header "Remaining findings after 2 fix-retry rounds" and continue to openspec-review.
- [ ] 3.2 Update `_run_review_fix_retry` to accept review results as a parameter (`review_results: list[ReviewResult]`) instead of extracting them from `stages` — this prevents picking up stale results from prior review rounds.

## 4. Tests

- [ ] 4.1 In `tests/test_review_agents.py`: update `test_only_medium_low_returns_false` — rename to `test_medium_returns_true`, change assertion to `assert triage_findings(...) is True`. Add `test_low_only_returns_true`.
- [ ] 4.2 In `tests/test_review_agents.py`: update `test_format_*` tests — verify all severities appear in feedback. Update footer assertion from "Fix the high/critical issues" to "Fix the issues above".
- [ ] 4.3 In `tests/test_pipeline_review.py`: rename `test_no_retry_path` to `test_medium_triggers_retry`. Change assertions: medium-only findings now trigger fix-retry (`len(worker_stages) == 2`).
- [ ] 4.4 In `tests/test_pipeline_review.py`: add `test_two_round_cap` — mock review agents to return findings on every round. Assert worker is dispatched 3 times (initial + 2 fix-retries). Assert a "Remaining findings" comment is posted.

## 5. Validation

```bash
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
```
