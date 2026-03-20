## Context

The harness currently stores skills in `.claude/skills/` and `.claude/commands/opsx/`, and interactive agents in `.claude/agents/`. These locations are Claude Code's native directories — they work when running Claude Code from within the harness repo, but don't travel to target repos.

Claude Code's plugin system provides exactly the layering we need: a plugin named `action` would namespace all harness skills as `/action:skill-name`, bundle agents for interactive use, and load automatically in any project where the plugin is installed.

The harness already has two categories of agents:
- **Pipeline agents** (`.harness/agents/`): Dispatched by the harness runtime as subprocesses. These are loaded via `agents.py` and don't need to be Claude Code agents.
- **Interactive agents** (`.claude/agents/`): Available in Claude Code's `/agents` menu for human use.

Only the interactive agents should move to the plugin. Pipeline agents stay where they are.

## Goals / Non-Goals

**Goals:**
- Package the harness as a Claude Code plugin with the `action` namespace
- Move all harness skills to the plugin's `skills/` directory
- Move interactive agents (spec-reviewer) to the plugin's `agents/` directory
- Remove legacy `.claude/commands/opsx/` and `.claude/skills/` directories
- Ensure the harness repo itself can still use its own skills during development (via `--plugin-dir .`)

**Non-Goals:**
- Publishing to a plugin marketplace (future work)
- Moving pipeline agents (`.harness/agents/`) — these are dispatched by the harness runtime, not Claude Code
- Changing skill behavior or adding new skills — this is purely a structural migration
- Changing the harness CLI or pipeline code — skills are prompt-based, not code

## Decisions

### Plugin name: `action`

Skills become `/action:opsx-propose`, `/action:dispatch-change`, `/action:repo-assess`, etc. Short, clear, no collision with target repo skills.

**Alternative considered:** `harness` — more descriptive but longer. `action` matches the package name (`action-harness`) and is the verb that matters.

### Skill naming: hyphen-separated, flat

Claude Code plugins support one level of namespacing: `plugin-name:skill-name`. No nested colons. Skills use kebab-case names:

| Current | Plugin |
|---------|--------|
| `/opsx:propose` | `/action:opsx-propose` |
| `/opsx:apply` | `/action:opsx-apply` |
| `/opsx:review` | `/action:opsx-review` |
| `/opsx:explore` | `/action:opsx-explore` |
| `/opsx:archive` | `/action:opsx-archive` |

New dispatch and repo skills (from harness-skills change) follow the same pattern:
- `/action:dispatch-change`, `/action:dispatch-prompt`, `/action:dispatch-issue`
- `/action:repo-assess`, `/action:repo-ready`, `/action:repo-report`

### Directory layout

```
action-harness/                    (repo root = plugin root)
├── .claude-plugin/
│   └── plugin.json               # {"name": "action", "description": "..."}
├── skills/                        # Plugin skills (was .claude/skills/)
│   ├── opsx-propose/
│   │   └── SKILL.md
│   ├── opsx-apply/
│   │   └── SKILL.md
│   ├── opsx-review/
│   │   └── SKILL.md
│   ├── opsx-explore/
│   │   └── SKILL.md
│   ├── opsx-archive/
│   │   └── SKILL.md
│   ├── dispatch-change/
│   │   └── SKILL.md
│   ├── dispatch-prompt/
│   │   └── SKILL.md
│   ├── dispatch-issue/
│   │   └── SKILL.md
│   ├── repo-assess/
│   │   └── SKILL.md
│   ├── repo-ready/
│   │   └── SKILL.md
│   └── repo-report/
│       └── SKILL.md
├── agents/                        # Plugin agents (interactive only)
│   └── spec-reviewer.md
├── .harness/                      # Pipeline agents (unchanged)
│   └── agents/
│       ├── bug-hunter.md
│       ├── test-reviewer.md
│       ├── quality-reviewer.md
│       ├── spec-compliance-reviewer.md
│       ├── openspec-reviewer.md
│       ├── spec-writer.md
│       └── lead.md
└── settings.json                  # Plugin default settings (optional)
```

**Key decisions:**
- The repo root IS the plugin root. No nested plugin directory.
- `.claude/skills/` and `.claude/commands/opsx/` are removed after migration.
- `.claude/agents/spec-reviewer.md` moves to `agents/spec-reviewer.md`.
- `.harness/agents/` stays in place — pipeline agents are loaded by `agents.py`, not by Claude Code's plugin system.

### Development workflow

During development on the harness repo itself, use `--plugin-dir .` to load the plugin from the local checkout. This means the harness repo's own skills are available during development without installation.

### Migration approach: move files, update names in frontmatter

Each skill's `name` field in SKILL.md frontmatter needs to drop the `openspec-` prefix and use the new naming. The directory name determines the skill name in the plugin namespace, so `skills/opsx-propose/SKILL.md` becomes `/action:opsx-propose`.

## Risks / Trade-offs

- **[Breaking change]** All existing `/opsx:*` invocations stop working → Mitigation: This only affects the harness repo's own development workflow. Target repos don't have these skills yet. Update all references (lead persona, HARNESS.md, CLAUDE.md) in the same change.
- **[Plugin system maturity]** Claude Code's plugin system is relatively new → Mitigation: The plugin structure is simple (static files). Fallback is `--plugin-dir` for local development.
- **[Two agent locations]** Pipeline agents in `.harness/agents/` and interactive agents in `agents/` could be confusing → Mitigation: Document clearly in CLAUDE.md. The distinction is real: pipeline agents are subprocess-dispatched, interactive agents are Claude Code-native.
