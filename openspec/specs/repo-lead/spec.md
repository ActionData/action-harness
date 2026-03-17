# repo-lead Specification

## Purpose
TBD - created by archiving change repo-lead. Update Purpose after archive.
## Requirements
### Requirement: Lead command spawns Claude Code session with repo context
The `harness lead --repo <path> "prompt"` command SHALL gather repo context and dispatch a Claude Code session with the repo-lead persona.

#### Scenario: Lead with prompt
- **WHEN** the user runs `harness lead --repo ./my-repo "What should we work on next?"`
- **THEN** the harness SHALL gather context (ROADMAP.md, issues, assessment) and dispatch a Claude Code session with the lead persona and context + prompt

#### Scenario: Lead with no prompt
- **WHEN** the user runs `harness lead --repo ./my-repo` without a prompt
- **THEN** the harness SHALL dispatch the lead with a default prompt: "Review the repo state and recommend what to work on next"

### Requirement: Context gathering
The lead SHALL receive pre-gathered context including repo files, issues, assessment scores, and recent run data.

#### Scenario: Full context available
- **WHEN** the repo has ROADMAP.md, CLAUDE.md, open issues, and prior harness runs
- **THEN** the lead's prompt SHALL include sections for roadmap, project context, open issues, assessment scores, and recent run summary

#### Scenario: Minimal context
- **WHEN** the repo has no ROADMAP.md, no CLAUDE.md, no prior runs
- **THEN** the lead SHALL still run with available context (issues, codebase) and recommend improving context as a first action

### Requirement: Lead persona loaded from agent definition
The lead agent persona SHALL be loaded from `.harness/agents/lead.md` using the existing agent file loading infrastructure.

#### Scenario: Lead persona loaded
- **WHEN** the lead is dispatched
- **THEN** the system prompt SHALL be loaded from `.harness/agents/lead.md` via `load_agent_prompt`

#### Scenario: Repo override
- **WHEN** the target repo has `.harness/agents/lead.md`
- **THEN** the repo's version SHALL be used instead of the harness default

### Requirement: --dispatch auto-dispatches recommended changes
The `--dispatch` flag SHALL parse the lead's output for dispatch recommendations and execute them via `harness run`.

#### Scenario: Auto-dispatch with recommendations
- **WHEN** `--dispatch` is provided and the lead recommends dispatching change `add-logging`
- **THEN** the harness SHALL run `harness run --change add-logging --repo <path>` as a subprocess

#### Scenario: No dispatch without flag
- **WHEN** `--dispatch` is not provided
- **THEN** the lead's recommendations SHALL be displayed but not executed

#### Scenario: Only existing changes dispatched
- **WHEN** the lead recommends dispatching a change that doesn't have OpenSpec artifacts (no `tasks.md`)
- **THEN** the harness SHALL skip that dispatch with a warning

#### Scenario: Multiple dispatches executed sequentially
- **WHEN** the lead recommends 3 dispatches
- **THEN** the harness SHALL execute them sequentially; a failure in one SHALL NOT prevent subsequent dispatches

#### Scenario: Dispatch failure reported
- **WHEN** a dispatched `harness run` exits non-zero
- **THEN** the harness SHALL log the failure with change name and exit code and continue

### Requirement: Handle repos without OpenSpec
The lead SHALL work on repos that don't have OpenSpec initialized.

#### Scenario: No OpenSpec directory
- **WHEN** the target repo has no `openspec/` directory
- **THEN** the lead SHALL still run using available context (issues, CLAUDE.md, codebase) and may recommend bootstrapping OpenSpec

### Requirement: JSON output
The lead SHALL output a structured JSON plan with proposals, issues, and dispatch recommendations.

#### Scenario: JSON plan output
- **WHEN** the lead completes and the `result` field contains extractable JSON
- **THEN** the harness SHALL extract the JSON via `extract_json_block` and validate it as a `LeadPlan` model with keys: `summary`, `proposals`, `issues`, `dispatches`

#### Scenario: No JSON in lead output
- **WHEN** the lead produces output with no extractable JSON plan
- **THEN** the harness SHALL display the raw output text to the user, log a warning, and `--dispatch` SHALL be a no-op

