#!/usr/bin/env bash
# Statusline script for Claude Code — shows whether the local repo
# is behind origin's default branch.  Designed to run after every
# Claude response; uses a 30-second cache to avoid excessive network calls.
#
# Output examples:
#   ✓ in sync          — local matches remote
#   ↓ behind origin    — remote has newer commits
#   ? sync unknown     — network error / could not check
#   (empty)            — not a git repo or no remote

set -euo pipefail

# --- Guard: must be inside a git repo with a remote -----------------------
git rev-parse --git-dir >/dev/null 2>&1 || exit 0
git remote get-url origin >/dev/null 2>&1 || exit 0

# --- Detect default branch ------------------------------------------------
detect_default_branch() {
    local ref
    ref=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null) && {
        echo "${ref##*/}"
        return
    }
    # Fallback: try main, then master
    if git rev-parse --verify "origin/main" >/dev/null 2>&1; then
        echo "main"
    elif git rev-parse --verify "origin/master" >/dev/null 2>&1; then
        echo "master"
    else
        return 1
    fi
}

DEFAULT_BRANCH=$(detect_default_branch) || exit 0

# --- Cache setup ----------------------------------------------------------
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
# Portable SHA-256: prefer sha256sum (Linux), fall back to shasum (macOS)
REPO_HASH=$(printf '%s' "$REPO_ROOT" | (sha256sum 2>/dev/null || shasum -a 256) | cut -c1-12)
CACHE_FILE="/tmp/harness-sync-cache-${REPO_HASH}"
CACHE_TTL=30  # seconds

# --- Read cache or fetch remote SHA ---------------------------------------
now=$(date +%s)
remote_sha=""
cache_hit=false

if [[ -f "$CACHE_FILE" ]]; then
    cache_ts=$(head -1 "$CACHE_FILE" 2>/dev/null || echo 0)
    age=$(( now - cache_ts ))
    if (( age < CACHE_TTL )); then
        cached_value=$(sed -n '2p' "$CACHE_FILE" 2>/dev/null || echo "")
        if [[ "$cached_value" == "NETWORK_ERROR" ]]; then
            echo "? sync unknown"
            exit 0
        fi
        remote_sha="$cached_value"
        cache_hit=true
    fi
fi

if [[ "$cache_hit" == false ]]; then
    # Network call — ls-remote is lightweight (single HTTP request)
    remote_sha=$(git ls-remote origin "refs/heads/${DEFAULT_BRANCH}" 2>/dev/null | cut -f1) || true
    if [[ -z "$remote_sha" ]]; then
        # Network failure — cache sentinel so we don't retry for CACHE_TTL
        printf '%s\nNETWORK_ERROR\n' "$now" > "$CACHE_FILE" 2>/dev/null || true
        echo "? sync unknown"
        exit 0
    fi
    # Write to cache.
    # Note: this write is not atomic — concurrent invocations could read a
    # partial file. Acceptable because the worst case is one extra ls-remote.
    printf '%s\n%s\n' "$now" "$remote_sha" > "$CACHE_FILE" 2>/dev/null || true
fi

# --- Compare to local SHA ------------------------------------------------
local_sha=$(git rev-parse "origin/${DEFAULT_BRANCH}" 2>/dev/null) || {
    echo "? sync unknown"
    exit 0
}

# Note: this comparison only detects "remote moved ahead". If local is ahead
# or diverged, it still shows "behind origin". This is intentional — the
# question we answer is "has main moved on origin?", not full ref topology.
if [[ "$local_sha" == "$remote_sha" ]]; then
    echo "✓ in sync"
else
    echo "↓ behind origin"
fi
