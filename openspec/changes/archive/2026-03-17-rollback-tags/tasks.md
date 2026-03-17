## 1. Tag Utilities [no dependencies]

- [x] 1.1 Create `src/action_harness/tags.py` with `create_tag(repo_path: Path, tag_name: str, commit: str = "HEAD") -> str` that creates a git tag and returns the actual tag name used. If tag already exists, append `-{YYYYMMDD-HHMMSS-ffffff}` (microsecond precision) and retry. If the timestamped tag also collides, raise an error with a clear message.
- [x] 1.2 Add `push_tag(repo_path: Path, tag_name: str) -> bool` that runs `git push origin <tag_name>` (pushing only this specific tag, NOT `--tags`). Returns True on success. On failure, logs a warning containing "push" to stderr and returns False without raising an exception.
- [x] 1.3 Add `list_tags(repo_path: Path, pattern: str) -> list[dict]` that returns tags matching a glob pattern with `tag` (str), `commit` (str matching `[0-9a-f]{7,40}`), `date` (ISO 8601 str), and `label` (str — the part after the last `/` in the tag name), sorted by date descending.
- [x] 1.4 Add `get_latest_tag(repo_path: Path, pattern: str) -> str | None` that returns the most recent tag matching the pattern, or None.
- [x] 1.5 Add tests: create tag succeeds, create with collision retries with timestamp, push success returns True, push failure returns False and logs warning (verify warning in stderr, verify no exception raised), list with 3 tags returns all sorted by date descending with correct fields, list empty returns empty list, get_latest returns most recent, get_latest with no matches returns None

## 2. Pre-merge Tagging [depends: 1]

- [x] 2.1 Add a `tag_pre_merge(repo_path: Path, label: str, base_branch: str) -> None` function that creates `harness/pre-merge/{label}` on the base branch HEAD and pushes the tag via `push_tag()`
- [x] 2.2 Call `tag_pre_merge()` in `pipeline.py` immediately before `create_pr()` (not after), using the base branch HEAD as the tag target. Use `change_name` as the label (which is either the real change name or prompt slug).
- [x] 2.3 Add tests: pre-merge tag created with correct name on correct commit (base branch HEAD, not worktree HEAD), tag pushed

## 3. Post-merge Tagging via CLI [depends: 1]

- [x] 3.1 Add a `tag_shipped(repo_path: Path, label: str, pr_url: str) -> bool` function that checks if the PR is merged via `gh pr view --json mergedAt,mergeCommitSha`, creates `harness/shipped/{label}` on the merge commit, and pushes the tag via `push_tag()`. Returns False if PR is not merged.
- [x] 3.2 Add `harness tag-shipped` command to `cli.py` with `--repo` (required Path), `--pr` (required str, the PR URL), `--label` (required str). Calls `tag_shipped()` and reports success or failure.
- [x] 3.3 Add tests: tag created when PR is merged (mock gh), no tag when PR is open, gh failure handled gracefully, invalid PR URL exits with error

## 4. Rollback Command [depends: 1]

- [x] 4.1 Add `harness rollback` command to `cli.py` with `--repo` (required), `--to` (optional tag name). If `--to` is not provided, use `get_latest_tag()` with pattern `harness/pre-merge/*`. Check for dirty working tree first — if `git status --porcelain` produces output, exit with error "Working tree has uncommitted changes. Commit or stash before rolling back."
- [x] 4.2 Implement rollback as: `git read-tree -m -u {tag}` to update index and working tree to match the tag, then `git commit -m "Rollback to {tag}"`. This produces a single clean forward commit regardless of intermediate merge commits. No `git revert`, no `--force`, no history rewriting.
- [x] 4.3 Add tests in a temp git repo: rollback to latest tag, rollback to specific tag, no tags exits with error, verify exactly one new commit is created (not force push), verify the tree after rollback matches the tagged tree, dirty working tree exits with error

## 5. History Command [depends: 1]

- [x] 5.1 Add `harness history` command to `cli.py` with `--repo` (required) and `--json` (flag). List all `harness/shipped/*` tags via `list_tags()`.
- [x] 5.2 Format terminal output: one line per tag with date, commit hash (short), and label. JSON output: array of objects.
- [x] 5.3 Add tests: history with 3 tags returns all 3 sorted by date descending, history empty says "No harness-shipped features found", `--json` output is valid JSON array where each object has keys `tag` (str), `commit` (str), `date` (ISO 8601 str), `label` (str), and ordering is date descending

## 6. Validation [depends: all]

- [x] 6.1 Run full test suite (`uv run pytest -v`) and verify no regressions
- [x] 6.2 Run lint and type checks (`uv run ruff check .` and `uv run mypy src/`)
- [x] 6.3 Integration smoke test in a temp git repo: create 2 commits, tag pre-merge, create 2 more commits, run rollback to the tag, verify HEAD tree matches the tagged tree. Then create a shipped tag and verify `list_tags("harness/shipped/*")` returns it with correct fields.
