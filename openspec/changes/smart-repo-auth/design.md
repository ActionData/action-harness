## Context

`_parse_repo_ref` in `repo.py` converts `owner/repo` shorthand to `https://github.com/owner/repo.git`. Private repos using SSH keys fail at clone time with "could not read Username for 'https://github.com': Device not configured."

## Goals / Non-Goals

**Goals:**
- `owner/repo` shorthand works for both public and private repos
- Detect auth method automatically via `gh auth status`
- Fall back to SSH when HTTPS clone fails

**Non-Goals:**
- Supporting non-GitHub hosts (GitLab, Bitbucket)
- Managing SSH keys or `gh auth login`
- Caching auth detection across runs

## Decisions

### 1. Check `gh auth status` for protocol detection

Run `gh auth status` and parse the output to determine if HTTPS auth (token) is configured. If `gh` is authenticated with a token, use HTTPS. Otherwise, default to SSH.

**Why:** `gh auth status` is the canonical way to check GitHub CLI auth. If the user has `gh` configured (which the harness already requires), this tells us the right protocol.

### 2. SSH fallback on HTTPS clone failure

If `_clone_or_fetch` fails with an HTTPS URL, retry with the SSH equivalent before raising `ValidationError`. Log the fallback to stderr.

**Why:** Some environments have both auth methods partially configured. Trying SSH as a fallback is cheap and handles edge cases without user intervention.

### 3. No explicit `--repo-protocol` flag for now

Keep it automatic. If the detection is wrong, the user can always pass the full URL. A flag adds complexity without clear need.

**Why:** YAGNI. The auto-detection handles the common cases.

## Risks / Trade-offs

**[Risk] `gh auth status` may not be installed or may have unexpected output format.**
→ Mitigation: If parsing fails, default to HTTPS (current behavior). SSH fallback catches private repos.
