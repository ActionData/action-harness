## 1. Repo Management Module

- [ ] 1.1 In `repo.py`: define `resolve_repo(repo_arg: str, harness_home: Path) -> Path` that takes the `--repo` argument and returns a local path. If `repo_arg` is an existing local directory, return it as-is. If it matches `owner/repo` pattern or starts with `https://` or `git@`, clone or locate the repo under `harness_home/repos/`. Return the path to the clone.
- [ ] 1.2 In `repo.py`: define `_parse_repo_ref(repo_arg: str) -> tuple[str, str, str]` returning `(owner, repo_name, clone_url)`. Handle GitHub shorthand (`owner/repo` → `https://github.com/owner/repo.git`), HTTPS URLs, and SSH URLs. Extract owner and repo_name from any form.
- [ ] 1.3 In `repo.py`: define `_get_repo_dir(owner: str, repo_name: str, harness_home: Path) -> Path` that returns the directory to clone into. Default to `harness_home/repos/<repo_name>/`. If a different repo already exists at that path (different origin URL), fall back to `harness_home/repos/<owner>-<repo_name>/` and log the collision.
- [ ] 1.4 In `repo.py`: define `_clone_or_fetch(clone_url: str, repo_dir: Path, verbose: bool) -> None`. If `repo_dir` doesn't exist, run `git clone <url> <repo_dir>`. If it does exist, run `git fetch origin` inside it. Log to stderr.

## 2. Workspace Paths in Worktree Module

- [ ] 2.1 In `worktree.py`: update `create_worktree` to accept an optional `workspace_dir: Path | None` parameter. If provided, create the worktree at `workspace_dir` instead of using `tempfile.mkdtemp`. If not provided, fall back to temp dir (preserves existing behavior for tests).
- [ ] 2.2 In `pipeline.py`: compute workspace path as `harness_home / "workspaces" / repo_name / change_name` and pass to `create_worktree`. When `--repo` is a local path (not managed), use temp dir as before.

## 3. CLI Updates

- [ ] 3.1 In `cli.py`: add `--harness-home` option (Path | None, default None). Resolve: CLI flag > `HARNESS_HOME` env var > `~/harness/`. Pass to pipeline.
- [ ] 3.2 In `cli.py`: update `--repo` handling to call `resolve_repo(repo_arg, harness_home)` before validation. Pass the resolved local path to `validate_inputs` and `run_pipeline`.
- [ ] 3.3 In `cli.py`: add `clean` subcommand with `--repo` (str, optional), `--change` (str, optional), `--all` (bool) options. Remove workspace directories and prune git worktrees.
- [ ] 3.4 In `cli.py`: update `--help` text to document that `--repo` accepts local paths, `owner/repo`, or full URLs.
- [ ] 3.5 In `cli.py`: update dry-run output to show the resolved repo path and workspace path.

## 4. Pipeline Updates

- [ ] 4.1 In `pipeline.py`: add `harness_home: Path | None = None` parameter to `run_pipeline`. When set, use it to compute workspace paths. Pass through to worktree creation.

## 5. Tests

- [ ] 5.1 In `tests/test_repo.py`: test `_parse_repo_ref` — GitHub shorthand, HTTPS URL, SSH URL. Verify owner, repo_name, clone_url extraction.
- [ ] 5.2 In `tests/test_repo.py`: test `resolve_repo` — local path passthrough, remote repo triggers clone (mock subprocess), already-cloned repo triggers fetch (mock subprocess).
- [ ] 5.3 In `tests/test_repo.py`: test `_get_repo_dir` — default path, collision detection with different origin URL.
- [ ] 5.4 In `tests/test_cli.py`: test `clean` subcommand — clean specific workspace, clean all for repo, clean all. Use tmp_path fixtures.
- [ ] 5.5 In `tests/test_worktree.py`: test `create_worktree` with explicit `workspace_dir` — worktree created at specified path, not in /tmp.

## 6. Validation

```bash
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
```
