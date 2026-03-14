## 1. Protection Module

- [ ] 1.1 Create `src/action_harness/protection.py`. Define `load_protected_patterns(repo_path: Path) -> list[str]` that reads `.harness/protected-paths.yml` from the repo. Parse YAML with `pyyaml` (already a dependency). Return the `protected` list. If file missing, log to stderr and return `[]`. If malformed YAML or missing `protected` key, log warning and return `[]`.
- [ ] 1.2 In `protection.py`: define `check_protected_files(changed_files: list[str], patterns: list[str]) -> list[str]` that matches each changed file against the patterns using `fnmatch.fnmatch`. Return the list of files that match any pattern.
- [ ] 1.3 In `protection.py`: define `get_changed_files(worktree_path: Path, base_branch: str) -> list[str]` that runs `git diff --name-only origin/<base_branch>..HEAD` in the worktree and returns the list of changed file paths. Return `[]` on failure.
- [ ] 1.4 In `protection.py`: define `flag_pr_protected(pr_url: str, protected_files: list[str], worktree_path: Path, verbose: bool) -> None` that posts a PR comment listing the protected files and adds the `protected-paths` label via `gh pr edit --add-label protected-paths`. Log to stderr. Non-fatal — swallow errors with warning.

## 2. Pipeline Integration

- [ ] 2.1 In `models.py`: add `protected_files: list[str] = []` field to `RunManifest`.
- [ ] 2.2 In `pipeline.py`: import from `protection`. After PR creation succeeds and before review agents, call `load_protected_patterns(repo)`, then `get_changed_files(worktree_path, base_branch)`, then `check_protected_files(changed, patterns)`. If protected files found, call `flag_pr_protected(pr_url, protected_files, worktree_path, verbose)`. Store the result for the manifest.
- [ ] 2.3 In `pipeline.py`: pass `protected_files` to `_build_manifest` and set on the manifest.
- [ ] 2.4 If structured logging is available (EventLogger), emit a `protection.checked` event with `metadata={"protected_files": protected_files, "patterns_count": len(patterns)}`.

## 3. Default Config

- [ ] 3.1 Create `.harness/protected-paths.yml` in this repo with default patterns:
  ```yaml
  protected:
    - "src/action_harness/pipeline.py"
    - "src/action_harness/evaluator.py"
    - "src/action_harness/worktree.py"
    - "src/action_harness/models.py"
    - "src/action_harness/cli.py"
    - "CLAUDE.md"
  ```

## 4. Tests

- [ ] 4.1 In `tests/test_protection.py`: test `load_protected_patterns` — file exists with patterns (returns list), file missing (returns []), malformed YAML (returns [], logs warning).
- [ ] 4.2 In `tests/test_protection.py`: test `check_protected_files` — exact match, glob match (`*.py`), no match returns `[]`, multiple matches.
- [ ] 4.3 In `tests/test_protection.py`: test `get_changed_files` — mock subprocess, returns file list. Test failure returns `[]`.
- [ ] 4.4 In `tests/test_protection.py`: test `flag_pr_protected` — mock subprocess, verify `gh pr comment` and `gh pr edit --add-label` are called. Test empty list does nothing.
- [ ] 4.5 In `tests/test_integration.py` or `tests/test_pipeline_review.py`: add test that verifies `manifest.protected_files` is populated when protected files are in the diff.

## 5. Validation

```bash
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
```
