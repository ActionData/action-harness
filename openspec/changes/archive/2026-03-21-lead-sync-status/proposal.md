## Why

The lead session gathers repo context at startup but has no visibility into whether the local repo drifts behind origin during a long session. When someone pushes to main (or the harness merges a PR), the lead is reading stale ROADMAP, openspec changes, and assessment state. There's no indicator to the human or the lead that this has happened, and no lightweight mechanism to sync without restarting the session.

## What Changes

- Add a Claude Code **statusline script** that shows whether the local repo is behind origin. Uses `git ls-remote origin HEAD` for a lightweight remote check, cached for 30 seconds to avoid hammering the network. Displays an indicator like `↑ behind origin/main by 3` or `in sync` at the bottom of every lead session.
- Add a **`/sync` skill** that the lead or user can invoke to pull latest changes. For user working trees: `git pull --ff-only`. For harness-owned clones: `git fetch origin && git reset --hard origin/<default-branch>`. The skill reports what changed after syncing.
- Update the **lead persona** to mention the sync skill: "When the status line shows the repo is behind origin, use `/sync` to pull latest before reading repo state or dispatching."

## Capabilities

### New Capabilities

- `lead-sync-status`: Statusline indicator for repo sync state and a `/sync` skill to pull latest, keeping the lead session's view of the repo current without restarting

### Modified Capabilities

- `lead-interactive`: Lead persona updated to reference the sync skill when the statusline shows the repo is behind

## Impact

- New statusline script at `.harness/statusline.sh`, configured via `.claude/settings.json`
- New `/sync` custom slash command at `.claude/commands/sync.md`
- Modification to `.harness/agents/lead.md` persona
- Minor Python change: `provision_clone` in `lead_registry.py` creates a `.harness-managed` marker file in clones for detection
- Depends on Claude Code's statusline feature and custom slash command system
