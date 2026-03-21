Sync this repository with origin by pulling the latest changes from the default branch. Follow these steps exactly:

## 1. Detect default branch

Run `git symbolic-ref refs/remotes/origin/HEAD` and extract the branch name (last component after `/`). If that fails, try `git rev-parse --verify origin/main` — if it succeeds, use `main`. Otherwise try `origin/master`. If none work, report the error and stop.

## 2. Record the current HEAD

Run `git rev-parse origin/<default-branch>` and save the SHA as `BEFORE_SHA` so you can report what changed after sync.

## 3. Detect repo type

Check whether a `.harness-managed` file exists in the repo root:
- If it **exists**: this is a harness-owned clone — proceed to step 4a
- If it **does not exist**: this is a user working tree — proceed to step 4b

## 4a. Harness clone sync

Run:
```bash
git fetch origin && git reset --hard origin/<default-branch>
```

Report the result. Skip the dirty-check — harness clones have no local changes to protect.

## 4b. User working tree sync

First check for uncommitted changes:
```bash
git status --porcelain
```

If there is any output, **abort** with this warning:
> ⚠️ Working tree has uncommitted changes. Commit or stash them before syncing.

If clean, run:
```bash
git pull --ff-only
```

If `git pull --ff-only` **fails** (exit code non-zero), report:
> ❌ Fast-forward failed — your branch has diverged from origin. Try `git pull --rebase` or resolve manually.

## 5. Invalidate statusline cache

After sync completes (success or failure), delete the statusline cache file so the next statusline invocation gets a fresh remote check:
```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
REPO_HASH=$(printf '%s' "$REPO_ROOT" | (sha256sum 2>/dev/null || shasum -a 256) | cut -c1-12)
rm -f "/tmp/harness-sync-cache-${REPO_HASH}"
```

## 6. Report summary

After a successful sync, compare the new `origin/<default-branch>` SHA to `BEFORE_SHA`:
- If they are the same: report "Already up to date."
- If they differ: run `git rev-list --count BEFORE_SHA..origin/<default-branch>` to get the number of new commits, and report:
  > ✓ Synced — pulled N new commit(s) from origin/<default-branch>
