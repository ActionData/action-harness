## Context

Workers dispatched to external repos cannot use OpenSpec skills because `.claude/skills/` doesn't exist in the target worktree. The harness needs to inject its skills before dispatch.

The pattern mirrors how `agents.py` resolves harness agent definitions: walk up from source to find the repo root, then fall back to package resources.

## Goals / Non-Goals

**Goals:**
- Discover harness skills from the harness source tree (`.claude/skills/`)
- Copy skill directories into the target worktree's `.claude/skills/` before dispatch
- Respect target repo precedence — never overwrite existing skills
- Write a `.harness-injected` marker listing injected skills for diagnostics
- Log injection at entry/exit to stderr per CLAUDE.md conventions
- Clean integration: one function call in the pipeline

**Non-Goals:**
- MCP server injection or tool configuration
- Skill versioning or dependency management
- Runtime skill loading (Claude Code handles that natively)
- Injecting skills for review agent dispatches (they don't need OpenSpec skills)
- Modifying the target repo's git state (injected files are in the worktree only, not committed)

## Decisions

### Copy entire skill directories, not individual files

**Decision:** Copy each skill directory (e.g., `openspec-apply-change/`) as a unit.

**Rationale:** Claude Code discovers skills by looking for `SKILL.md` inside directories under `.claude/skills/`. Copying directory-by-directory preserves the expected structure and allows multi-file skills (if any exist in the future).

### Target repo skills always win

**Decision:** If the target repo already has a skill directory with the same name, skip it.

**Rationale:** The target repo may have customized versions of skills. The harness should add missing skills, never replace existing ones. This matches the agent definition precedence pattern in `agents.py`.

### Marker file for diagnostics

**Decision:** Write `.claude/skills/.harness-injected` listing injected skill names.

**Rationale:** When debugging worker issues, it's useful to know which skills were injected vs. native. The marker file is lightweight and ignored by Claude Code (it only looks for directories containing `SKILL.md`).

### Resolve source skills using the same walk-up pattern as agents.py

**Decision:** Walk up from `__file__` to find the harness repo root, then read `.claude/skills/`.

**Rationale:** Consistent with `resolve_harness_agents_dir()` in `agents.py`. Works in both source checkout and development scenarios.

### Inject before dispatch, not at worktree creation

**Decision:** Skill injection happens in `_run_pipeline_inner` between worktree creation and worker dispatch.

**Rationale:** Worktree creation is a git operation that shouldn't know about Claude Code skills. Injection is a pre-dispatch concern. Placing it in the pipeline makes the dependency explicit and keeps `worktree.py` focused on git operations.

## File Layout

```
src/action_harness/
  skills.py          # NEW: skill discovery and injection
  pipeline.py        # MODIFIED: call inject_skills() before dispatch
  worker.py          # UNCHANGED

tests/
  test_skills.py     # NEW: unit tests
```
