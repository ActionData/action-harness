## Context

The lead session runs as a Claude Code subprocess. It gathers context once at startup via `gather_lead_context()`, but during a long session the repo can drift behind origin (merged PRs, harness dispatches, human pushes). The lead has no signal that its view of the repo is stale, and no lightweight way to sync without restarting.

Claude Code's statusline feature runs a shell script after each response, displaying persistent output at the bottom of the terminal. This is the right mechanism — no tmux, no custom TUI, just a shell script that Claude Code already knows how to run.

## Goals / Non-Goals

**Goals:**
- Show a persistent sync status indicator at the bottom of lead sessions
- Provide a `/sync` skill the lead or user can invoke to pull latest
- Keep the network cost low — cache remote checks, don't fetch on every response
- Work for both user working trees (safe, no force) and harness clones (hard reset OK)

**Non-Goals:**
- Auto-syncing without user/lead action — too risky for working trees with local changes
- Replacing the startup sync in `lead_start` — that stays as-is for the initial context gather
- Providing a full dashboard like Gastown's `gt feed` — this is one indicator, not a TUI
- Showing status for multiple repos — scoped to the current working directory

## Decisions

### 1. `git ls-remote origin refs/heads/<default-branch>` for remote check, not `git fetch`

`ls-remote` is a single lightweight HTTP request — returns the remote SHA with no object transfer. We query the explicit branch ref (`refs/heads/main`) rather than `HEAD` to avoid ambiguity when `origin/HEAD` is unconfigured. Compare to `git rev-parse origin/<default-branch>` (local, instant). If they differ, we know the default branch has moved on origin since the last fetch.

The comparison is always against the default branch, regardless of what branch the user is on. This answers the question "has main moved?" — which is what matters for lead context freshness — not "is my feature branch behind?".

**Default branch detection:** `git symbolic-ref refs/remotes/origin/HEAD`, falling back to `main`, then `master`. Same logic used in `sync_repo()` in `lead_registry.py`.

**Why not `git fetch`?** Fetch downloads objects and updates refs — too expensive to run every 30 seconds. We only need to know *if* the default branch has moved, not *by how much*. The `/sync` skill does the actual fetch when the user decides to act.

**Alternative considered:** `git status -b --porcelain` — only shows behind count relative to the *last fetch*, not actual remote state. Useless if nobody has fetched recently.

### 2. Cache for 30 seconds in a temp file

The statusline script runs after every Claude response (debounced at 300ms). Without caching, `ls-remote` would hit the network constantly. A 30-second TTL cache (write SHA + timestamp to `/tmp/harness-sync-cache-<repo-hash>`) balances freshness with cost.

### 3. Statusline script shipped as `.harness/statusline.sh`, configured via `.claude/settings.json`

The script lives in the harness repo at `.harness/statusline.sh`. It is configured via the repo's `.claude/settings.json` with the `"statusLine"` key:

```json
{
  "statusLine": {
    "type": "command",
    "command": ".harness/statusline.sh"
  }
}
```

This applies to all Claude Code sessions in the repo, not just lead sessions. That's acceptable — the sync indicator is useful in any session, and Claude Code has no mechanism to scope statusline config to specific session types.

### 4. `/sync` as a Claude Code custom slash command

A `.claude/commands/sync.md` file that the lead or user invokes via `/sync`. It detects whether the current repo is a harness-owned clone by checking for a `.harness-managed` marker file in the repo root (created by the lead registry's `provision_clone`). This avoids hardcoding `~/.harness/` and works with configurable harness home directories.

### 5. Lead persona gets a one-line instruction, not a procedure

The persona update is minimal: "When the status line shows the repo is behind origin, run `/sync` before reading repo state or dispatching." No need for detailed instructions — the skill handles the logic.

## Risks / Trade-offs

- **`ls-remote` requires network access** → If offline, the statusline gracefully shows "?" or skips the indicator. The script handles network errors silently.
- **30s cache means up to 30s lag** → Acceptable. The indicator is advisory, not real-time. The user can always run `/sync` manually.
- **`git pull --ff-only` can fail on diverged branches** → The sync skill logs the error and suggests `git pull --rebase` or manual resolution. It never force-pulls on user working trees.
- **Statusline adds a subprocess per response** → Cached path is just a file read + timestamp check — sub-millisecond. Network path is one HTTP request every 30s — negligible.
