## Why

When using `--repo owner/repo` shorthand, the harness always generates an HTTPS clone URL (`https://github.com/owner/repo.git`). This fails for private repos where the user's auth is configured via SSH keys, not HTTPS tokens. The user has to manually specify the full SSH URL (`git@github.com:owner/repo.git`) as a workaround.

The harness should detect the available auth method and pick the right protocol automatically, or fall back to SSH when HTTPS fails.

## What Changes

- When `owner/repo` shorthand is used, check `gh auth status` to determine if HTTPS auth is available
- If HTTPS auth is available, use HTTPS URL (current behavior)
- If not, use SSH URL (`git@github.com:owner/repo.git`)
- If HTTPS clone fails, fall back to SSH before reporting failure
- Support explicit protocol preference via `--repo-protocol ssh|https` flag (optional)

## Capabilities

### New Capabilities

- `smart-repo-auth`: Automatic protocol detection for repo cloning. Uses `gh auth status` to pick HTTPS vs SSH, with SSH fallback on HTTPS failure.

### Modified Capabilities

## Impact

- `src/action_harness/repo.py` — update `_parse_repo_ref` and `_clone_or_fetch` for protocol detection and fallback
- `tests/test_repo.py` — tests for auth detection and fallback
