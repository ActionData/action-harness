## Why

The harness's skills, agents, and rules are locked inside its own repo. When leading a target repo, the lead session has harness skills available (because it runs from the harness repo context), but workers in target repo worktrees only get what's been manually injected. There's no clean boundary between harness-provided operational knowledge and target repo domain knowledge, leading to naming collisions, inconsistent availability, and no override mechanism.

Claude Code's plugin system solves this directly — plugins provide namespaced skills (`action:skill-name`), bundled agents, hooks, and settings that load automatically in any project.

## What Changes

- Package the harness as a Claude Code plugin with `action` as the plugin name
- Move harness skills from `.claude/skills/` and `.claude/commands/` to `skills/` at the plugin root
- Move harness agent definitions to `agents/` at the plugin root (interactive agents available via `/agents` menu)
- Pipeline agents (`.harness/agents/`) remain in place — they're dispatched by the harness runtime, not Claude Code's agent system
- Add `.claude-plugin/plugin.json` manifest with plugin metadata
- Add plugin `settings.json` for default configuration
- All harness skills become `/action:skill-name` (e.g., `/action:opsx-propose`, `/action:dispatch-change`, `/action:repo-assess`)
- Target repos add their own skills/agents independently — no collision with the `action:` namespace
- Remove the legacy `.claude/commands/opsx/` directory and `.claude/skills/` directory (migrated to plugin structure)

## Capabilities

### New Capabilities
- `plugin-structure`: Plugin manifest, directory layout, and skill migration from `.claude/` to plugin root
- `plugin-agents`: Agent definitions bundled with the plugin for interactive use (spec-writer, spec-reviewer)

### Modified Capabilities
- `harness-dispatch-skills`: Skill invocation paths change from `/opsx:propose` to `/action:opsx-propose` etc.
- `harness-repo-skills`: Same namespace migration
- `lead-skill-integration`: Lead persona references updated to use `/action:` prefixed skill names

## Impact

- **Skills**: All existing `/opsx:*` skills move to `/action:opsx-*`. Users need to update muscle memory but old names stop working.
- **Agents**: Interactive agents (spec-writer, spec-reviewer) become plugin-provided. Pipeline agents (bug-hunter, test-reviewer, quality-reviewer, etc.) stay in `.harness/agents/` unchanged.
- **Lead persona**: References to skill names in the lead persona prompt need updating.
- **HARNESS.md**: Worker instructions referencing skill names need updating.
- **Installation**: Users install the plugin once (`claude plugin install` or `--plugin-dir`) and it's available everywhere.
