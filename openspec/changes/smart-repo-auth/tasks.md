## 1. Auth Detection

- [ ] 1.1 In `repo.py`: add `_detect_gh_protocol() -> str` that runs `gh auth status` and parses the output. Return `"https"` if a token is detected, `"ssh"` otherwise. If `gh` is not available or the command fails, return `"https"` (default).
- [ ] 1.2 In `repo.py:_parse_repo_ref`: when the input matches `owner/repo` shorthand, call `_detect_gh_protocol()`. If `"ssh"`, generate `git@github.com:owner/repo.git` instead of the HTTPS URL. Explicit SSH/HTTPS URLs (not shorthand) bypass this detection.

## 2. Clone Fallback

- [ ] 2.1 In `repo.py:_clone_or_fetch`: when `git clone` fails with an HTTPS URL, construct the SSH equivalent (`https://github.com/owner/repo.git` → `git@github.com:owner/repo.git`) and retry. Log the fallback to stderr. If SSH also fails, raise `ValidationError` with the SSH error. Skip fallback for non-GitHub URLs or already-SSH URLs.

## 3. Tests

- [ ] 3.1 In `tests/test_repo.py`: test `_detect_gh_protocol` — mock subprocess for gh auth status with token output (returns "https"), without token (returns "ssh"), gh not found (returns "https").
- [ ] 3.2 In `tests/test_repo.py`: test `_parse_repo_ref` with shorthand — when protocol is "ssh", generates SSH URL. When protocol is "https", generates HTTPS URL.
- [ ] 3.3 In `tests/test_repo.py`: test clone fallback — HTTPS fails, SSH succeeds (mock subprocess). Both fail, raises ValidationError with SSH error.
- [ ] 3.4 In `tests/test_repo.py`: test explicit URLs bypass detection — `git@github.com:user/repo.git` and `https://github.com/user/repo` are used as-is.

## 4. Validation

```bash
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
```
