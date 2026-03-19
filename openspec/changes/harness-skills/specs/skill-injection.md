## Name

skill-injection

## Description

Discover harness skills and inject them into target repo worktrees before worker dispatch. Target repo skills take precedence.

## Requirements

1. `resolve_harness_skills_dir()` returns the path to `.claude/skills/` in the harness source tree, using the same walk-up pattern as `resolve_harness_agents_dir()` in `agents.py`.

2. `discover_skills(skills_dir)` returns a list of skill directory names (directories containing a `SKILL.md` file).

3. `inject_skills(source_dir, worktree_path, verbose)` copies harness skill directories into `worktree_path/.claude/skills/`, skipping any that already exist. Returns a list of injected skill names. Writes a `.harness-injected` marker file listing what was injected.

4. When the target worktree already has a skill directory with the same name, it is never overwritten.

5. All I/O functions log at entry and exit to stderr using `typer.echo(..., err=True)`.

6. Errors reading source skills (OSError, UnicodeDecodeError) are logged and result in an empty injection (non-fatal — the worker can still run, just without skills).

7. Pipeline integration: `_run_pipeline_inner` calls `inject_skills()` after worktree creation and before worker dispatch.
