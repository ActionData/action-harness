Prerequisites: implement after `worker-config` and `enrich-pr-description` (both modify `run_pipeline` signature and CLI). The `run_pipeline` signature will already include `model`, `effort`, `max_budget_usd`, `permission_mode`, `worker_result`, and `base_branch` parameters when this change is implemented.

## 1. Repo Management Module

- [x] 1.1 Create `src/action_harness/repo.py`. Define `resolve_repo(repo_arg: str, harness_home: Path, verbose: bool = False) -> tuple[Path, str]` that takes the `--repo` argument and returns `(local_path, repo_name)`. If `repo_arg` is an existing local directory, return `(Path(repo_arg), Path(repo_arg).name)`. If it matches `owner/repo` pattern or starts with `https://` or `git@`, clone or locate the repo under `harness_home/repos/` and return the clone path with the repo name. Raise `ValidationError` if clone fails.
- [x] 1.2 In `repo.py`: define `_parse_repo_ref(repo_arg: str) -> tuple[str, str, str]` returning `(owner, repo_name, clone_url)`. Handle GitHub shorthand (`owner/repo` → `https://github.com/owner/repo.git`), HTTPS URLs, and SSH URLs. Extract owner and repo_name from any form.
- [x] 1.3 In `repo.py`: define `_get_repo_dir(owner: str, repo_name: str, harness_home: Path) -> Path` that returns the directory to clone into. Default to `harness_home/repos/<repo_name>/`. To check for collision, run `git -C <existing_dir> remote get-url origin` and compare against the incoming `clone_url`. If they differ, use `harness_home/repos/<owner>-<repo_name>/` and log the collision to stderr.
- [x] 1.4 In `repo.py`: define `_clone_or_fetch(clone_url: str, repo_dir: Path, verbose: bool) -> None`. If `repo_dir` doesn't exist, run `git clone <url> <repo_dir>`. If it does exist, run `git fetch origin` inside it. Log to stderr. If clone fails, raise `ValidationError` with the git error message.

## 2. Workspace Paths in Worktree Module

- [x] 2.1 In `worktree.py`: update `create_worktree` to accept an optional `workspace_dir: Path | None` parameter. If provided, create the worktree at `workspace_dir` instead of using `tempfile.mkdtemp`. If not provided, fall back to temp dir (preserves existing behavior for tests).
- [x] 2.2 In `worktree.py`: update `cleanup_worktree` to handle both temp-dir and harness-home workspace paths. The current `parent.name.startswith("action-harness-")` guard at line ~180 only cleans temp dirs. Generalize: when the workspace is under harness home, remove the workspace directory directly (not the parent). When under temp, use existing behavior.
- [x] 2.3 In `pipeline.py`: add `repo_name: str | None = None` parameter to `run_pipeline`. When `harness_home` and `repo_name` are both set, compute workspace path as `harness_home / "workspaces" / repo_name / change_name` and pass to `create_worktree`. When `--repo` is a local path (not managed), use temp dir as before.

## 3. CLI Updates

- [x] 3.1 In `cli.py`: add `--harness-home` option (Path | None, default None). Resolve: CLI flag > `HARNESS_HOME` env var > `~/harness/`. Pass to pipeline.
- [x] 3.2 In `cli.py`: update `--repo` handling to call `resolve_repo(repo_arg, harness_home)` before validation. Unpack `(resolved_path, repo_name)`. Pass both to `validate_inputs` and `run_pipeline`.
- [x] 3.3 In `cli.py`: add `clean` subcommand with `--repo` (str, optional), `--change` (str, optional), `--all` (bool) options. For each workspace being cleaned: (1) resolve the repo string to the clone path under `harness_home/repos/` using `resolve_repo`, (2) run `git worktree remove` for the workspace, (3) remove the workspace directory, (4) run `git worktree prune` in the clone dir. Log actions to stderr.
- [x] 3.4 In `cli.py`: update `--help` text to document that `--repo` accepts local paths, `owner/repo`, or full URLs.
- [x] 3.5 In `cli.py`: update dry-run output to show the resolved repo path and workspace path. Replace the hardcoded `/tmp/action-harness/worktrees/harness/{change}` with the computed workspace path from `harness_home / "workspaces" / repo_name / change_name`.

## 4. Pipeline Updates

- [x] 4.1 In `pipeline.py`: add `harness_home: Path | None = None` and `repo_name: str | None = None` parameters to `run_pipeline`. Thread `harness_home` and `repo_name` to workspace computation in task 2.3.

## 5. Tests

- [ ] 5.1 In `tests/test_repo.py`: test `_parse_repo_ref` — GitHub shorthand (`user/repo` → owner, name, clone URL), HTTPS URL, SSH URL. Verify owner, repo_name, clone_url extraction for each form.
- [ ] 5.2 In `tests/test_repo.py`: test `resolve_repo` — local path passthrough (returns path and name), remote repo triggers clone (mock subprocess), already-cloned repo triggers fetch (mock subprocess), clone failure raises ValidationError.
- [ ] 5.3 In `tests/test_repo.py`: test `_get_repo_dir` — default path when no collision, collision detection via `git remote get-url origin` returning a different URL (mock subprocess), fallback to `owner-repo` dir name.
- [ ] 5.4 In `tests/test_cli.py`: test `clean` subcommand — clean specific workspace (directory removed), clean all for repo, clean all. Use tmp_path fixtures. Verify git worktree prune is called.
- [ ] 5.5 In `tests/test_worktree.py`: test `create_worktree` with explicit `workspace_dir` — worktree created at specified path, not in /tmp. Test `cleanup_worktree` works for both temp and harness-home paths.

## 6. Validation

```bash
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
```
