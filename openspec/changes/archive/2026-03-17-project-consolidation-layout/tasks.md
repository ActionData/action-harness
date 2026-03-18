## 1. Project Directory Setup

- [x] 1.1 Add `ensure_project_dir(harness_home: Path, repo_name: str) -> Path` to `repo.py`. Creates `projects/<repo_name>/` with subdirectories `repo/`, `workspaces/`, `runs/`, `knowledge/` if they don't exist. Returns the project directory path.
- [x] 1.2 Add `write_project_config(project_dir: Path, repo_name: str, remote_url: str | None) -> None` to `repo.py`. Writes `config.yaml` with `repo_name` and `remote_url` fields via `yaml.dump`. Only writes if `config.yaml` does not already exist (no overwrite on subsequent runs).
- [x] 1.3 Update `resolve_repo()` in `repo.py`: change clone destination from `harness_home / "repos" / repo_name` (line 106) to `project_dir / "repo"` (where `project_dir = ensure_project_dir(harness_home, repo_name)`). Call `write_project_config` after successful clone.
- [x] 1.4 Update collision fallback in `resolve_repo()`: change from `harness_home / "repos" / f"{owner}-{repo_name}"` (line 130) to `harness_home / "projects" / f"{owner}-{repo_name}" / "repo"`.

## 2. Workspace Path Updates

- [x] 2.1 In `pipeline.py`, update workspace path construction from `harness_home / "workspaces" / repo_name / change_name` (line 342) to `harness_home / "projects" / repo_name / "workspaces" / change_name`. Only apply when `harness_home` is set (managed repos). Local repos continue using `/tmp/`.
- [x] 2.2 In `cli.py`, update single-workspace clean path from `harness_home / "workspaces" / repo_name / task_label` (line 345) to `harness_home / "projects" / repo_name / "workspaces" / task_label`.
- [x] 2.3 In `cli.py`, restructure `_clean_all_workspaces` (line 699). Currently receives `workspaces_root` and iterates `workspaces/<repo>/`. Change to: iterate `harness_home / "projects" / */`, for each project iterate `workspaces/*/`, and find the clone at `projects/<name>/repo/` for worktree pruning (currently looks at `repos_dir = harness_home / "repos"` on line 701).
- [x] 2.4 In `cli.py`, update `clean --repo` to clean `projects/<name>/workspaces/` instead of `workspaces/<name>/`. Update the call site at line 479 that passes `workspaces_root = resolved_home / "workspaces"`.

## 3. Managed Repo Detection

- [x] 3.1 In `cli.py`, update `_is_managed_repo()` (line 433) to check `repo_path.resolve().relative_to(harness_home.resolve() / "projects")` instead of `harness_home.resolve() / "repos"`.
- [x] 3.2 In `cli.py`, update the dry-run workspace path display (line 345) from `workspaces / repo_name / task_label` to `projects / repo_name / workspaces / task_label`.

## 4. Run Manifest + Event Log Path

- [x] 4.1 In `pipeline.py`, update `_write_manifest()` (line 200): add optional `project_runs_dir: Path | None = None` parameter. When `project_runs_dir` is set (managed repo), write manifest to `project_runs_dir / f"{run_id}.json"`. When None (local repo), keep existing behavior (`repo / ".action-harness" / "runs"`).
- [x] 4.2 In `pipeline.py`, update `run_pipeline()` event log path (line 357): `runs_dir = repo / ".action-harness" / "runs"`. For managed repos, set `runs_dir` to `harness_home / "projects" / repo_name / "runs"`. Thread this through to `_write_manifest` and event log initialization.
- [x] 4.3 In `reporting.py`, update `load_manifests()` (line 88): add optional `runs_dir: Path | None = None` parameter. When set, read from that directory. When None, fall back to `repo_path / ".action-harness" / "runs"` (existing behavior for local repos).
- [x] 4.4 In `cli.py` `report` command (line 771-783): for managed repos, compute `runs_dir = resolved_home / "projects" / repo_name / "runs"` and pass to `load_manifests(repo, since=since, runs_dir=runs_dir)`. Detect managed by checking if `resolved_home / "projects"` contains the repo.
- [x] 4.5 In `progress_feed.py`, update `find_latest_event_log()` (line 94) and `find_event_log_for_run()` (line 125): both read from `repo_path / ".action-harness" / "runs"`. Add optional `runs_dir` parameter with same pattern as `load_manifests`.

## 5. Knowledge / Catalog Path

- [x] 5.1 In `pipeline.py`, update catalog frequency path from `harness_home / "repos" / repo_name / "knowledge"` (line 532) to `harness_home / "projects" / repo_name / "knowledge"`.
- [x] 5.2 In `cli.py` `report` command, update frequency path from `resolved_home / "repos" / repo_name / "knowledge" / "findings-frequency.json"` (line 800) to `resolved_home / "projects" / repo_name / "knowledge" / "findings-frequency.json"`.

## 6. Dashboard Updates

- [x] 6.1 In `dashboard.py`, update `list_repos` (line 241) to scan `harness_home / "projects"` instead of `harness_home / "repos"`. A directory is a managed project only if `config.yaml` exists. The repo clone is at `project_dir / "repo"`.
- [x] 6.2 In `dashboard.py`, update `list_workspaces` (line 214) to scan `harness_home / "projects" / <name> / "workspaces"` instead of `harness_home / "workspaces" / <name>`.
- [x] 6.3 In `dashboard.py`, update `repo_detail` (line 299) to read from `projects/<name>/repo/` for HARNESS.md, protected-paths, and OpenSpec data.
- [x] 6.4 In `dashboard.py`, update `cross_repo_roadmap` (line 372) to iterate `harness_home / "projects"` instead of `harness_home / "repos"`, filter by `config.yaml` existence, and read openspec data from `entry / "repo" / "openspec/"`.

## 7. CLI repos show

- [x] 7.1 In `cli.py`, update `repos show` command (line 980): change `repo_dir = resolved_home / "repos" / name` to `repo_dir = resolved_home / "projects" / name`. Check `repo_dir / "config.yaml"` exists. Update error message to reference `projects/` path.

## 8. Branch Protection

- [x] 8.1 Verify `branch_protection.py` has no filesystem `repos/` references to update. Note: `repos/` on line 84 is a GitHub API URL path (`repos/{owner_repo}/branches/...`), not a filesystem path — no changes needed.

## 9. Tests

- [x] 9.1 Test `ensure_project_dir`: call with temp harness home and `"test-app"`. Assert `projects/test-app/` exists with subdirectories `repo/`, `workspaces/`, `runs/`, `knowledge/`. Assert `config.yaml` does not exist yet.
- [x] 9.2 Test `write_project_config`: call with temp project dir, `repo_name="test-app"`, `remote_url="git@github.com:user/test-app.git"`. Assert `config.yaml` exists, parse it, assert `repo_name == "test-app"` and `remote_url` matches. Call again — assert file content unchanged (no overwrite).
- [x] 9.3 Test workspace path for managed repo: mock a managed repo run. Assert worktree path is `projects/<name>/workspaces/<change>/` not `workspaces/<name>/<change>/`.
- [x] 9.4 Test workspace path for local repo: run with `--repo .`. Assert worktree is created in `/tmp/` (unchanged behavior).
- [x] 9.5 Test manifest written to project runs dir for managed repo: mock a managed repo pipeline completion. Assert manifest file exists at `projects/<name>/runs/<run-id>.json`. Assert manifest JSON is valid and parseable. Assert NO manifest at `<worktree>/.action-harness/runs/`.
- [x] 9.6 Test manifest written to worktree for local repo: mock a local repo pipeline completion. Assert manifest at `<worktree>/.action-harness/runs/<run-id>.json` (unchanged).
- [x] 9.7 Test `list_repos` scans `projects/` with config gating: create temp harness home with `projects/foo/config.yaml` and `projects/bar/config.yaml` and `projects/broken/` (no config). Assert `list_repos` returns 2 repos (foo, bar). Assert `broken` is not returned. Assert each `RepoSummary.path` points to `projects/<name>/repo/`.
- [x] 9.8 Test `_is_managed_repo` returns True for `projects/<name>/repo/` path and False for local paths.
- [x] 9.9 Test clean removes workspace from project dir: create `projects/app/workspaces/fix-bug/`. Run clean logic. Assert directory removed.
- [x] 9.10 Test `load_manifests` with explicit `runs_dir`: create temp dir with 2 manifest JSON files. Call `load_manifests(repo_path, runs_dir=temp_dir)`. Assert returns 2 manifests. Call without `runs_dir` — assert falls back to `.action-harness/runs/`.

## 10. Self-Validation

- [x] 10.1 `uv run pytest tests/ -v` — all existing and new tests pass
- [x] 10.2 `uv run ruff check .` — no lint errors
- [x] 10.3 `uv run ruff format --check .` — formatting clean
- [x] 10.4 `uv run mypy src/` — no type errors
- [x] 10.5 `uv run action-harness repos --help` — shows help
- [x] 10.6 `uv run action-harness clean --help` — shows help
- [x] 10.7 `uv run action-harness report --help` — shows help
