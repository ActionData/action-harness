## 1. Statusline Script

- [x] 1.1 Create `.harness/statusline.sh` script that detects the default branch (`git symbolic-ref refs/remotes/origin/HEAD`, fallback `main` then `master`), runs `git ls-remote origin refs/heads/<default-branch>` (with cache), compares to local `git rev-parse origin/<default-branch>`, and outputs a sync status indicator
- [x] 1.2 Implement 30-second cache using a temp file at `/tmp/harness-sync-cache-<hash>` where hash is SHA-256 of the absolute repo path truncated to 12 hex characters, storing remote SHA and timestamp
- [x] 1.3 Handle edge cases: not a git repo (omit indicator), no remote (omit indicator), network failure (show neutral indicator), default branch detection failure (try `main` then `master`)

## 2. Sync Command

- [x] 2.1 Create `.claude/commands/sync.md` custom slash command that detects whether the repo is a harness-owned clone (`.harness-managed` marker file in repo root) or a user working tree
- [x] 2.2 For user working trees: check for uncommitted changes first (abort with warning if dirty), then run `git pull --ff-only`, report result, handle diverged-branch failure with actionable suggestion
- [x] 2.3 For harness clones: run `git fetch origin && git reset --hard origin/<default-branch>`, report result
- [x] 2.4 After sync, report summary: number of new commits pulled

## 3. Lead Persona Update

- [x] 3.1 Add sync instruction to `.harness/agents/lead.md`: "When the status line shows the repo is behind origin, run `/sync` before reading repo state or dispatching"
- [x] 3.2 Add `/sync` to the lead's capabilities list in the persona

## 4. Configuration

- [x] 4.1 Add statusline configuration to `.claude/settings.json` with `"statusLine": {"type": "command", "command": ".harness/statusline.sh"}`
- [ ] 4.2 Add `.harness-managed` marker file creation to `provision_clone` in `lead_registry.py` so harness-owned clones are identifiable
- [ ] 4.3 Verify statusline script works in a live lead session — indicator appears, updates after responses, cache prevents excessive network calls
