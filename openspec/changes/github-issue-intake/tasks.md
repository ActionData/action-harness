## 1. Issue Reading Module [no dependencies]

- [x] 1.1 Create `src/action_harness/issue_intake.py` with a `IssueData` NamedTuple (or dataclass): `title: str`, `body: str`, `state: str`. Add `read_issue(issue_number: int, repo_path: Path) -> IssueData` that runs `gh issue view <number> --json title,body,state` via subprocess, parses JSON, and returns `IssueData`. Raise `ValidationError` if gh returns non-zero (issue not found) or `state == "CLOSED"` (issue already closed).
- [x] 1.2 Add `detect_openspec_change(body: str, repo_path: Path) -> str | None` that scans the issue body for patterns using regex: `openspec:([a-z0-9-]+)`, `change:\s*([a-z0-9-]+)`, `openspec/changes/([a-z0-9-]+)`. For the first match found, check if `repo_path / "openspec" / "changes" / name` directory exists. Return the name if it exists, None otherwise.
- [x] 1.3 Add `build_issue_prompt(issue_number: int, title: str, body: str) -> str` that returns `f"# GitHub Issue #{issue_number}: {title}\n\n{body}"`.
- [x] 1.4 Add tests: `read_issue` success (mock gh returning `{"title": "Fix bug", "body": "Details...", "state": "OPEN"}`), issue not found (mock gh exit 1, assert `ValidationError`), issue closed (state=CLOSED, assert `ValidationError` with "already closed"). `detect_openspec_change("See openspec:add-logging", repo)` returns `"add-logging"` when directory exists. `detect_openspec_change("change: fix-auth", repo)` returns `"fix-auth"` when directory exists. `detect_openspec_change("openspec/changes/new-feature/", repo)` returns `"new-feature"`. Pattern found but directory missing returns None. No pattern returns None. Multiple patterns returns the first match. `build_issue_prompt(42, "Fix bug", "Details")` equals `"# GitHub Issue #42: Fix bug\n\nDetails"`.

## 2. Issue Status Labels [depends: 1]

- [x] 2.1 Add `label_issue(issue_number: int, label: str, repo_path: Path, verbose: bool = False) -> None` that runs `gh issue edit <number> --add-label <label>` via subprocess. Log warning on failure via `typer.echo(..., err=True)`, never raise.
- [x] 2.2 Add `comment_on_issue(issue_number: int, body: str, repo_path: Path, verbose: bool = False) -> None` that runs `gh issue comment <number> --body <body>` via subprocess. Log warning on failure, never raise.
- [x] 2.3 Add tests: label success (mock gh exit 0), label failure is non-fatal (mock gh exit 1, verify no exception raised, verify warning logged). Comment success/failure similarly.

## 3. CLI Integration [depends: 1]

Prerequisites: `unspecced-tasks` must be merged first. This change assumes `--change` is already optional (`typer.Option(None, ...)`), `--prompt` exists, and `slugify_prompt()` is available — all introduced by `unspecced-tasks`.

- [x] 3.1 Add `--issue` option (`int | None`, default None) to the `run` command in `cli.py`. Update the existing two-way mutual exclusion (from `unspecced-tasks`) to three-way: if more than one of `--change`, `--prompt`, `--issue` is provided, exit with "Specify only one of --change, --prompt, or --issue". If none provided, exit with "Specify one of --change, --prompt, or --issue".
- [x] 3.2 When `--issue` is used: call `read_issue(issue, resolved_repo)` to get `IssueData`. Call `detect_openspec_change(issue_data.body, resolved_repo)` to check for change reference. If change found, set `change = detected_name` and proceed as `--change` mode. If no change found, import `slugify_prompt` from the worker/utils module, compute `task_label = f"prompt-{slugify_prompt(issue_data.title)}"` as the change name, and set `prompt = build_issue_prompt(issue, issue_data.title, issue_data.body)`.
- [x] 3.3 Pass `issue_number: int | None` through to `run_pipeline()` for PR linking and labeling.
- [x] 3.4 Update `run()` docstring and help text to document `--issue`: "Run the action-harness pipeline from an OpenSpec change, freeform prompt, or GitHub issue."
- [x] 3.5 Update the `--dry-run` block to handle `--issue` mode: print the issue number, resolved mode (change or prompt), and the computed change name or prompt preview.
- [x] 3.6 Add CLI tests: `--issue` alone works (mock read_issue), `--issue` with `--change` exits with error, `--issue` with `--prompt` exits with error, `--help` includes `--issue`, `--dry-run` with `--issue` shows issue number and resolved mode.

## 4. PR Linking [depends: 3]

- [x] 4.1 Add `issue_number: int | None = None` parameter to `run_pipeline()`, `_run_pipeline_inner()`, and `create_pr()`. In `create_pr()`, pass `issue_number` through to `_build_pr_body()`. In `_build_pr_body()`, when `issue_number` is set, append `\n\nCloses #<number>` to the PR body.
- [x] 4.2 Add tests: PR body includes `Closes #42` when `issue_number=42` is set. PR body unchanged when `issue_number` is None.

## 5. Pipeline Issue Labeling [depends: 2, 3]

- [ ] 5.1 In `_run_pipeline_inner()`, when `issue_number` is set: call `label_issue(issue_number, "harness:in-progress", repo)` at pipeline start (after worktree creation). After `create_pr()` succeeds, call `label_issue(issue_number, "harness:pr-created", repo)` and `comment_on_issue(issue_number, f"PR created: {pr_result.pr_url}", repo)`.
- [ ] 5.2 Add tests: verify `label_issue` called with `"harness:in-progress"` at pipeline start and `"harness:pr-created"` after PR creation (mock). Verify labeling failure doesn't fail pipeline (mock gh exit 1, pipeline still succeeds).

## 6. Validation [depends: all]

- [ ] 6.1 Run full test suite (`uv run pytest -v`) and verify no regressions
- [ ] 6.2 Run lint and type checks (`uv run ruff check .` and `uv run mypy src/`)
- [ ] 6.3 Run `harness run --issue 1 --repo . --dry-run` and verify output shows issue number, resolved mode, and computed change/prompt (requires a real or mock issue; if no issue exists, verify the error message is clear).
