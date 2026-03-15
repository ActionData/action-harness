## 1. Auth Detection

- [x] 1.1 In `repo.py`: add `_detect_gh_protocol() -> str` that runs `gh auth token` (not `gh auth status` — more stable output). If exit code is 0 (token exists), return `"https"`. If exit code is non-zero, return `"ssh"`. If `gh` is not available (FileNotFoundError), return `"https"` (default).
- [x] 1.2 In `repo.py:resolve_repo`: after `_parse_repo_ref` returns for shorthand input, call `_detect_gh_protocol()`. If `"ssh"`, swap the clone URL from HTTPS to SSH: `https://github.com/owner/repo.git` → `git@github.com:owner/repo.git`. Keep `_parse_repo_ref` pure (no subprocess calls) — it always returns the HTTPS URL for shorthand. The protocol swap happens in `resolve_repo`. Existing tests for `_parse_repo_ref` remain unchanged.

## 2. Clone Fallback

- [x] 2.1 In `repo.py:_clone_or_fetch`: when `git clone` fails with an HTTPS GitHub URL, construct the SSH equivalent and retry. Log the fallback to stderr. If SSH also fails, raise `ValidationError` mentioning both errors. Skip fallback for non-GitHub URLs or already-SSH URLs. After a successful SSH fallback, update the remote URL: `git remote set-url origin <ssh_url>` — this prevents collision detection mismatch on the next run.
- [x] 2.2 The fallback applies to all HTTPS GitHub clone failures, including explicit HTTPS URLs (not just shorthand). Update the "Explicit SSH/HTTPS URLs bypass detection" spec: detection is bypassed but fallback still applies to HTTPS clones.

## 3. Tests

- [x] 3.1 In `tests/test_repo.py`: test `_detect_gh_protocol` — mock subprocess for `gh auth token`: exit 0 returns "https", exit 1 returns "ssh", FileNotFoundError returns "https".
- [x] 3.2 In `tests/test_repo.py`: test `resolve_repo` with shorthand — mock `_detect_gh_protocol` to return "ssh", verify clone URL is SSH. Mock to return "https", verify HTTPS. Assert `_parse_repo_ref` is NOT mocked (still returns HTTPS — swap happens in `resolve_repo`).
- [x] 3.3 In `tests/test_repo.py`: test clone fallback — HTTPS fails, SSH succeeds (mock subprocess). Assert `git remote set-url origin` was called with SSH URL. Both fail, raises ValidationError with both errors.
- [x] 3.4 In `tests/test_repo.py`: test explicit SSH URL — assert `_detect_gh_protocol` is NOT called (use mock `assert_not_called`). Explicit HTTPS — assert detection not called but fallback still applies on failure.

## 4. Validation

```bash
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
```
