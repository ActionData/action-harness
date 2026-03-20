# plugin-agents Specification

## Purpose
TBD - created by archiving change action-plugin. Update Purpose after archive.
## Requirements
### Requirement: Interactive agents bundled with plugin
The plugin SHALL provide interactive agent definitions in the `agents/` directory at the plugin root. These agents SHALL appear in Claude Code's `/agents` menu when the plugin is installed.

#### Scenario: Spec reviewer agent available
- **WHEN** the action plugin is installed and the user opens the agents menu
- **THEN** the `spec-reviewer` agent SHALL be available for selection

#### Scenario: Legacy interactive agent directory removed
- **WHEN** the migration is complete
- **THEN** `.claude/agents/spec-reviewer.md` SHALL NOT exist (moved to `agents/spec-reviewer.md`)

### Requirement: Pipeline agents remain in .harness/agents
Pipeline agents dispatched by the harness runtime (bug-hunter, test-reviewer, quality-reviewer, spec-compliance-reviewer, openspec-reviewer, spec-writer, lead) SHALL remain in `.harness/agents/` and SHALL NOT be moved to the plugin `agents/` directory.

#### Scenario: Pipeline agents unchanged
- **WHEN** the migration is complete
- **THEN** `.harness/agents/` SHALL contain all pipeline agent definitions (bug-hunter.md, test-reviewer.md, quality-reviewer.md, spec-compliance-reviewer.md, openspec-reviewer.md, spec-writer.md, lead.md)

#### Scenario: Pipeline agent loading unaffected
- **WHEN** the harness runtime loads a pipeline agent via `load_agent_prompt()`
- **THEN** it SHALL resolve from `.harness/agents/` as before, with no change to the resolution logic

