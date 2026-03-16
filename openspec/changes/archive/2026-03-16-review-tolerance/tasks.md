## 1. Models and Constants

- [x] 1.1 Add `SEVERITY_RANK` and `TOLERANCE_THRESHOLD` constants to `review_agents.py`: `SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}`, `TOLERANCE_THRESHOLD = {"low": 0, "med": 1, "high": 2}`
- [x] 1.2 Add `AcknowledgedFinding` model to `models.py` with fields: `finding: ReviewFinding` (the original finding), `acknowledged_in_round: int` (the round number where it was first flagged but not fixed)
- [x] 1.3 Add `tolerance: str | None` field to `ReviewResult` model to record the tolerance level used for triage in that round. Default `None` for backward compatibility.

## 2. Tolerance-Based Triage

- [x] 2.1 Add `filter_actionable_findings(results: list[ReviewResult], tolerance: str) -> list[ReviewFinding]` to `review_agents.py` — returns findings where `SEVERITY_RANK[finding.severity] >= TOLERANCE_THRESHOLD[tolerance]`
- [x] 2.2 Update `triage_findings(results: list[ReviewResult], tolerance: str) -> bool` to accept tolerance parameter and return `True` only when actionable findings exist at or above the tolerance threshold
- [x] 2.3 Update `format_review_feedback(results: list[ReviewResult], tolerance: str, prior_acknowledged: list[AcknowledgedFinding] | None = None) -> str` to include only actionable findings in the main section and append a "Prior Acknowledged Findings" section listing any prior acknowledged findings
- [x] 2.4 Add acknowledgment protocol instructions to the feedback prompt text: "For each finding, you MUST either fix it in code or post a PR comment explaining why no change is needed. If a finding appears under Prior Acknowledged Findings, add a code comment at the relevant location — two reviewers flagging the same concern means future readers will too."

## 3. CLI Flag

- [x] 3.1 Add `--review-cycle` option to `cli.py` `run` command — comma-separated string, default `low,med,high`
- [x] 3.2 Add validation: split on comma, each element must be one of `low`, `med`, `high`; exit with error on invalid input showing valid values
- [x] 3.3 Thread `review_cycle: list[str]` parameter through to `_run_pipeline_inner`

## 4. Pipeline Review Loop

- [x] 4.1 Refactor the review stage in `pipeline.py` to iterate over `review_cycle` list instead of `range(2)`. Each iteration passes the current round's tolerance to triage and feedback formatting.
- [x] 4.2 Implement short-circuit: break out of review cycle when a round produces zero actionable findings after tolerance filtering
- [x] 4.3 Implement `match_findings(prior: list[ReviewFinding], current: list[ReviewFinding]) -> list[ReviewFinding]` in `review_agents.py`. Two findings match if they share the same `file` field AND either (a) the same `agent` field, or (b) one finding's `title` is a case-insensitive substring of the other's. Returns the subset of current findings that match any prior finding.
- [x] 4.4 Integrate acknowledged finding tracking into the pipeline loop: after each fix-retry, call `match_findings` with the round's pre-fix actionable findings and the post-fix review findings. Wrap matched findings as `AcknowledgedFinding` and accumulate across rounds.
- [x] 4.5 Pass accumulated `prior_acknowledged` list to `format_review_feedback` in subsequent rounds
- [x] 4.6 Update verification review to filter at the last round's tolerance level

## 5. PR Comment Updates

- [x] 5.1 Ensure `_post_review_comment` receives the full unfiltered `review_results` (all findings at all severities) while `_run_review_fix_retry` receives only the actionable subset. Add severity label tags (e.g., `[LOW]`, `[HIGH]`) to each finding in the PR comment.
- [x] 5.2 Add tolerance level and round number to review comment headers (e.g., "Review round 1/3 (tolerance: low)")

## 6. Tests

- [x] 6.1 Test `filter_actionable_findings` at each tolerance level: create 4 `ReviewFinding` objects with severities low, medium, high, critical. At tolerance `low`, assert all 4 returned. At `med`, assert 3 returned (medium, high, critical). At `high`, assert 2 returned (high, critical).
- [x] 6.2 Test `triage_findings` with tolerance: create results with only low-severity findings. Assert `triage_findings(results, "low")` returns `True`. Assert `triage_findings(results, "med")` returns `False`. Assert `triage_findings(results, "high")` returns `False`. With empty findings, assert `False` at all tolerance levels.
- [x] 6.3 Test `format_review_feedback` filtering: create results with 1 high and 2 low findings. At tolerance `med`, assert feedback contains the high finding text and does not contain the low finding text. With `prior_acknowledged` containing one `AcknowledgedFinding`, assert feedback contains a "Prior Acknowledged Findings" section with that finding's details.
- [x] 6.4 Test CLI validation: invoke `run` with `--review-cycle foo` and assert exit code is nonzero with error message containing "low", "med", "high". Invoke with `--review-cycle low,high` and assert no validation error.
- [x] 6.5 Test `match_findings`: create prior finding (file="a.py", title="Missing null check", agent="bug-hunter") and current finding (file="a.py", title="Missing null check on return", agent="quality-reviewer"). Assert match (title substring). Create current finding (file="b.py", title="Missing null check"). Assert no match (different file).
- [x] 6.6 Test `match_findings` with same agent: create prior finding (file="a.py", title="Unused import", agent="quality-reviewer") and current finding (file="a.py", title="Unclear naming", agent="quality-reviewer"). Assert match (same file + same agent, even though titles differ).

## 7. Self-Validation

- [x] 7.1 `uv run pytest tests/ -v` — all existing and new tests pass
- [x] 7.2 `uv run ruff check .` — no lint errors
- [x] 7.3 `uv run ruff format --check .` — formatting clean
- [x] 7.4 `uv run mypy src/` — no type errors
- [x] 7.5 `uv run action-harness run --review-cycle high --dry-run --change test --repo .` — dry-run output shows 1 review round at tolerance `high`
