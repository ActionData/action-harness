## 1. Data Models

- [x] 1.1 Add `RepoSummary` model to `models.py`: `name: str`, `path: Path`, `remote_url: str | None`, `has_harness_md: bool`, `has_protected_paths: bool`, `workspace_count: int`, `stale_workspace_count: int`, `active_changes: int`, `completed_changes: int`
- [x] 1.2 Add `WorkspaceInfo` model to `models.py`: `repo_name: str`, `change_name: str`, `path: Path`, `branch: str`, `last_commit_age_days: int`, `has_open_pr: bool`, `stale: bool`
- [x] 1.3 Add `ChangeInfo` model to `models.py`: `name: str`, `status: Literal["active", "completed"]`, `progress_pct: float`, `task_count: int`, `tasks_complete: int`
- [x] 1.4 Add `RepoDetail` model to `models.py`: `summary: RepoSummary`, `harness_md_content: str | None`, `protected_patterns: list[str]`, `workspaces: list[WorkspaceInfo]`, `roadmap_content: str | None`, `openspec_changes: list[ChangeInfo]`, `completed_changes: int`
- [x] 1.5 Add `RepoRoadmap` model to `models.py`: `repo_name: str`, `roadmap_content: str | None`, `active_changes: list[ChangeInfo]`, `completed_count: int`

## 2. Data Layer

- [x] 2.1 Create `src/action_harness/dashboard.py` with `list_repos(harness_home: Path) -> list[RepoSummary]` — scan `repos/` dir, skip non-git directories (no `.git`), read git remote URL via `git remote get-url origin` (None on failure), check for HARNESS.md and `.harness/protected-paths.yml`, count workspaces and OpenSpec changes
- [x] 2.2 Add `repo_detail(harness_home: Path, repo_name: str) -> RepoDetail` — read HARNESS.md content (or None), parse protected-paths.yml using `load_protected_patterns` from `protection.py`, list workspaces with staleness, read roadmap, enumerate OpenSpec changes with progress, count completed changes
- [x] 2.3 Add `list_workspaces(harness_home: Path) -> list[WorkspaceInfo]` — scan `workspaces/<repo_name>/<change_name>/` dirs (two-level nesting), get branch name from `git rev-parse --abbrev-ref HEAD`, compute last commit age via `git log -1 --format=%ct`, check for open PR via `gh pr list --head <branch> --json number --limit 1` (best-effort, set `has_open_pr=False` on failure)
- [x] 2.4 Add `cross_repo_roadmap(harness_home: Path) -> list[RepoRoadmap]` — for each repo, read `openspec/ROADMAP.md` content and enumerate active changes with progress
- [x] 2.5 Add `read_openspec_changes(repo_path: Path) -> tuple[list[ChangeInfo], int]` — scan `openspec/changes/` for active changes (excluding `archive/` and hidden dirs), count `- [x]` vs `- [ ]` lines in each `tasks.md` for progress, count subdirectories in `openspec/changes/archive/` for completed count. Return `(active_changes, completed_count)`
- [x] 2.6 Add `read_roadmap(repo_path: Path) -> str | None` — read `openspec/ROADMAP.md` or return None

## 3. CLI Commands

- [x] 3.1 Add `repos` sub-app to `cli.py` using `typer.Typer(name="repos")` and `app.add_typer(repos_app)`. Use `@repos_app.callback(invoke_without_command=True)` so `harness repos` (no subcommand) runs the listing logic. Check `ctx.invoked_subcommand is not None` to skip listing when a subcommand is invoked.
- [x] 3.2 Add `show` command on `repos_app` — `@repos_app.command()` with `name: str` argument. Calls `repo_detail()` and prints formatted output. Exits with error `"Repo '<name>' not found in <harness_home>/repos/"` if repo dir doesn't exist.
- [x] 3.3 Add `workspaces` top-level command on `app` — calls `list_workspaces()` and prints formatted output
- [x] 3.4 Add `roadmap` top-level command on `app` — calls `cross_repo_roadmap()` and prints formatted output
- [x] 3.5 Add `--json` flag (typer `Option`, default `False`) to all four commands — when set, print `model.model_dump_json(indent=2)` instead of formatted text

## 4. Formatting

- [x] 4.1 Implement formatted text output for `repos` list — each repo on one line with aligned columns: `<name>  HARNESS.md: ✓/✗  Protected: ✓/✗  Workspaces: N  Changes: N active`
- [x] 4.2 Implement formatted text output for `repos show` — sections separated by headers (═══): HARNESS.md content (or "Not configured"), Protected Patterns (bullet list or "None"), Workspaces (with `(stale)` marker), Roadmap (content or "No roadmap"), OpenSpec Changes (progress bars: `◉ name  [████░░░░░░] N%`)
- [x] 4.3 Implement formatted text output for `workspaces` — grouped by repo name header, each workspace shows: `<change_name>  <branch>  <N>d ago  (stale)?`
- [x] 4.4 Implement formatted text output for `roadmap` — grouped by repo name header, active changes with progress bars matching `openspec view` style (`◉`/`✓` indicators, `[████░░░░]` bars). Repos without OpenSpec show "No OpenSpec".

## 5. Tests

- [x] 5.1 Test `list_repos` with a mock harness home containing 2 repo dirs (one with HARNESS.md, one without), each initialized as a git repo. Assert returns 2 `RepoSummary` with correct `has_harness_md` values. Also create `workspaces/repo1/change1/` and `openspec/changes/active1/` in one repo. Assert `workspace_count=1` and `active_changes=1`.
- [x] 5.2 Test `list_repos` skips non-git directories. Create a plain directory (no `.git`) in `repos/`. Assert it is not included in the returned list.
- [x] 5.3 Test `repo_detail` reads HARNESS.md content correctly. Create a temp repo dir with a 5-line HARNESS.md. Assert `harness_md_content` matches file content.
- [x] 5.4 Test `repo_detail` reads protected patterns. Create `.harness/protected-paths.yml` with `protected: ["src/core/**", "*.toml"]`. Assert `protected_patterns == ["src/core/**", "*.toml"]`.
- [x] 5.5 Test `read_openspec_changes` with a mock `openspec/changes/` dir containing a change with `tasks.md` that has 3 `- [x]` and 2 `- [ ]` lines. Assert `task_count=5`, `tasks_complete=3`, `progress_pct=60.0`. Also create `archive/` with 2 subdirectories. Assert `completed_count=2`.
- [x] 5.6 Test `read_openspec_changes` with no `openspec/` dir. Assert returns empty list and `completed_count=0`.
- [x] 5.7 Test `read_roadmap` with an existing `openspec/ROADMAP.md`. Assert returns file content. Test with no file. Assert returns None.
- [x] 5.8 Test `cross_repo_roadmap` with 2 mock repos (one with OpenSpec, one without). Assert returns 2 `RepoRoadmap` objects, one with changes and roadmap content, one with `roadmap_content=None` and empty changes.
- [x] 5.9 Test workspace staleness: create a mock workspace, mock `git log -1 --format=%ct` to return a timestamp 10 days ago, mock `gh pr list` to return empty list. Assert `stale=True`.
- [x] 5.10 Test workspace not stale with open PR: same as 5.9 but mock `gh pr list` to return `[{"number": 42}]`. Assert `stale=False`.
- [x] 5.11 Test `list_repos` with empty `repos/` dir. Assert returns empty list.

## 6. Self-Validation

- [ ] 6.1 `uv run pytest tests/ -v` — all existing and new tests pass
- [ ] 6.2 `uv run ruff check .` — no lint errors
- [ ] 6.3 `uv run ruff format --check .` — formatting clean
- [ ] 6.4 `uv run mypy src/` — no type errors
- [ ] 6.5 Create a temp directory with `repos/test-repo/` initialized as a git repo. Run `HARNESS_HOME=<temp> uv run action-harness repos` and assert exit code 0 and output contains `test-repo`.
- [ ] 6.6 `uv run action-harness workspaces --help` — shows help text
- [ ] 6.7 `uv run action-harness roadmap --help` — shows help text
