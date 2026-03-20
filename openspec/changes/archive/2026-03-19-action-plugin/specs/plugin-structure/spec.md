## ADDED Requirements

### Requirement: Plugin manifest
The harness repo root SHALL contain a `.claude-plugin/plugin.json` file with `"name": "action"` that registers the harness as a Claude Code plugin. All skills in the `skills/` directory SHALL be namespaced as `/action:skill-name`.

#### Scenario: Plugin manifest exists
- **WHEN** the harness repo is loaded as a Claude Code plugin
- **THEN** `.claude-plugin/plugin.json` SHALL exist with at minimum `{"name": "action"}` and a `description` field

#### Scenario: Skills are namespaced
- **WHEN** a user installs the action plugin and invokes a skill
- **THEN** all harness skills SHALL be available under the `/action:` namespace (e.g., `/action:opsx-propose`)

### Requirement: Skills directory at plugin root
All harness skills SHALL reside in `skills/` at the repo root (the plugin root), with each skill in its own subdirectory containing a `SKILL.md` file. The legacy `.claude/skills/` and `.claude/commands/opsx/` directories SHALL be removed.

#### Scenario: Skill files migrated
- **WHEN** the plugin is loaded
- **THEN** each skill directory under `skills/` SHALL contain a `SKILL.md` with valid frontmatter including `name` and `description` fields

#### Scenario: Legacy directories removed
- **WHEN** the migration is complete
- **THEN** `.claude/skills/` SHALL NOT exist and `.claude/commands/opsx/` SHALL NOT exist

### Requirement: Skill name mapping
Skills SHALL be renamed from their legacy names to plugin-compatible names during migration. The directory name determines the skill name in the plugin namespace.

#### Scenario: OpenSpec skills renamed
- **WHEN** the legacy `openspec-propose` skill is migrated
- **THEN** it SHALL be at `skills/opsx-propose/SKILL.md` and invokable as `/action:opsx-propose`

#### Scenario: All skills have consistent naming
- **WHEN** listing all skills in the `skills/` directory
- **THEN** each skill directory SHALL use kebab-case naming without the `openspec-` prefix (e.g., `opsx-propose` not `openspec-propose`)
