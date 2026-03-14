## Why

The harness currently requires you to clone a repo yourself, cd into it, and run `action-harness run --repo .`. This couples the harness to the developer's local checkout and puts worktrees in `/tmp` where they're invisible and ephemeral. To work on a new repo, you need to clone it, install dependencies, and know the eval commands.

The harness should manage repos and workspaces itself — clone from a URL or GitHub shorthand, create persistent workspaces, and let the agent work in a full repo environment with all tools and context available (CLAUDE.md, .claude/ skills, MCP config, etc.).

## What Changes

- Accept `--repo` as either a local path (existing behavior) or a GitHub URL / `owner/repo` shorthand
- When given a remote repo, clone it to `~/harness/repos/<repo-name>/` (configurable via `HARNESS_HOME` env var or `--harness-home` flag, default `~/harness/`)
- Create workspaces at `~/harness/workspaces/<repo-name>/<change-name>/` instead of `/tmp`
- Worker agents run in the workspace (a git worktree) which has full access to repo tools, skills, and config
- Add `action-harness clean` command to remove workspaces after PRs are merged
- Self-hosting invocation changes from `--repo .` to `--repo ActionData/action-harness`

## Capabilities

### New Capabilities

- `workspace-management`: Clone repos from GitHub URLs, manage persistent workspaces per repo per change, configurable harness home directory, workspace cleanup command.

### Modified Capabilities

## Impact

- `src/action_harness/cli.py` — `--repo` accepts URLs, new `clean` subcommand, `--harness-home` option
- `src/action_harness/worktree.py` — workspace paths change from `/tmp` to harness home
- New module `src/action_harness/repo.py` — clone management, URL parsing, fetch
- `CLAUDE.md` — document new invocation pattern
