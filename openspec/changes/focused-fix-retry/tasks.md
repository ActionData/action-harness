## 1. Priority Scoring [no dependencies]

- [x] 1.1 Add `compute_finding_priority(finding: ReviewFinding, all_findings: list[ReviewFinding]) -> int` to `review_agents.py`. Computes `SEVERITY_RANK[finding.severity] * 10 + cross_agent_count`. `cross_agent_count` is the number of distinct `agent` values among findings that share the same `file` AND have a case-insensitive title substring overlap with this finding.
- [x] 1.2 Add `select_top_findings(findings: list[ReviewFinding], max_findings: int) -> tuple[list[ReviewFinding], list[ReviewFinding]]` to `review_agents.py`. Returns `(selected, deferred)` — selected sorted by priority descending, capped at `max_findings`. If `max_findings <= 0`, return all findings as selected (no cap).
- [x] 1.3 Add tests with specific assertions: (a) Given critical finding (`cross_agent_count=1`) and medium finding (`cross_agent_count=3`), assert critical priority `3*10+1=31` > medium priority `1*10+3=13`. (b) Two high-severity findings, one with `cross_agent_count=3` and one with `cross_agent_count=1`, assert the 3-agent one ranks first. (c) Cross-agent detection: findings `("null check missing in handler", "foo.py", "bug-hunter")` and `("Missing null check", "foo.py", "quality-reviewer")` — assert `cross_agent_count=2` for both ("null check" is substring of both). (d) No overlap: `("race condition", "foo.py", "bug-hunter")` and `("unused import", "foo.py", "quality-reviewer")` — assert `cross_agent_count=1` for both. (e) `select_top_findings` with `max_findings=0` returns all as selected, empty deferred. (f) `max_findings=5` with 3 findings returns 3 selected, 0 deferred. (g) `max_findings=5` with 12 findings returns 5 selected, 7 deferred.

## 2. Integrate into format_review_feedback [depends: 1]

- [x] 2.1 Add `max_findings: int = 0` parameter to `format_review_feedback()`. When `max_findings > 0`, replace the `actionable` list with `selected, deferred = select_top_findings(actionable, max_findings)` and format only `selected`. Log deferred count to stderr: `typer.echo(f"[review] deferred {len(deferred)} finding(s) below priority cap", err=True)`. Preserve the existing group-by-agent formatting structure — just operate on the selected subset.
- [x] 2.2 Add tests: `format_review_feedback` with `max_findings=3` includes only 3 findings in output text. With `max_findings=0` includes all (backward compatible). Deferred findings NOT in feedback text but still in the original `results` objects.

## 3. CLI Flag [depends: 1]

- [x] 3.1 Add `--max-findings-per-retry` option (int, default 5) to `cli.py` `run` command. Thread through to `run_pipeline()`.
- [x] 3.2 Update dry-run output to show `max-findings-per-retry: N`.
- [x] 3.3 Update `run()` docstring.
- [x] 3.4 Add tests: `--help` shows the flag, dry-run with custom value shows it, default value is 5.

## 4. Pipeline Threading [depends: 2, 3]

- [x] 4.1 Add `max_findings_per_retry: int = 5` to `run_pipeline()`, `_run_pipeline_inner()`, AND `_run_review_fix_retry()`. Thread through the full call chain: `_run_pipeline_inner` passes `max_findings_per_retry` to `_run_review_fix_retry()` at the call site. `_run_review_fix_retry` passes `max_findings=max_findings_per_retry` to `format_review_feedback()`. Do NOT pass to `_post_review_comment` — PR comments show all findings.
- [x] 4.2 Add tests: pipeline with `max_findings_per_retry=2` — verify `format_review_feedback` called with `max_findings=2`. Pipeline with default (no flag) — verify `format_review_feedback` called with `max_findings=5`. Verify PR comment still contains all findings (not capped).

## 5. Validation [depends: all]

- [x] 5.1 Run `uv run pytest -v` — all tests pass
- [x] 5.2 Run `uv run ruff check .` and `uv run mypy src/` — clean
