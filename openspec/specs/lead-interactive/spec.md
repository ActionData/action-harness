# lead-interactive Specification

## Purpose
TBD - created by archiving change lead-interactive. Update Purpose after archive.
## Requirements
### Requirement: Interactive lead session with repo context
The `harness lead --repo <path>` command SHALL spawn an interactive Claude Code session by default, pre-loaded with the lead persona and gathered repo context. The lead persona SHALL instruct the agent to greet the user with a role explanation, capability overview, and state-aware suggestions. When onboarding gaps are detected, the lead SHALL offer to run onboarding before proceeding. When the statusline indicates the repo is behind origin, the lead SHALL use `/sync` before reading repo state or dispatching.

#### Scenario: Default interactive session
- **WHEN** the user runs `harness lead --repo ./my-repo`
- **THEN** the harness SHALL gather repo context, then spawn `claude` (without `-p`) with the lead persona as `--system-prompt` and repo context as `--append-system-prompt`

#### Scenario: Interactive session with initial prompt
- **WHEN** the user runs `harness lead --repo ./my-repo "Focus on test gaps"`
- **THEN** the harness SHALL pass the prompt as a positional argument to `claude` so the session starts with that message

#### Scenario: Interactive session inherits terminal
- **WHEN** an interactive lead session is spawned
- **THEN** the subprocess SHALL inherit stdin, stdout, and stderr so the human can interact naturally with the Claude Code session

#### Scenario: Greeting includes role and capabilities
- **WHEN** an interactive lead session starts without a user prompt
- **THEN** the lead agent SHALL produce a greeting that explains its role in the harness, lists capability categories, and suggests concrete next steps grounded in repo state

#### Scenario: Lead persona includes sync instruction
- **WHEN** the lead persona is loaded from `.harness/agents/lead.md`
- **THEN** the persona SHALL contain an instruction to run `/sync` when the status line shows the repo is behind origin, before reading repo state or dispatching

### Requirement: Non-interactive mode preserves existing behavior
The `--no-interactive` flag SHALL trigger the existing one-shot dispatch that produces a JSON plan.

#### Scenario: Non-interactive dispatch
- **WHEN** the user runs `harness lead start --repo ./my-repo --no-interactive`
- **THEN** the harness SHALL dispatch via `claude -p` and parse the JSON plan output (existing behavior)

#### Scenario: Dispatch requires non-interactive
- **WHEN** the user runs `harness lead start --repo ./my-repo --dispatch`
- **THEN** the harness SHALL automatically use non-interactive mode since `--dispatch` requires structured output

### Requirement: Interactive and dispatch are mutually exclusive
The `--interactive` flag and `--dispatch` flag SHALL NOT be used together.

#### Scenario: Explicit interactive with dispatch errors
- **WHEN** the user runs `harness lead start --repo ./my-repo --interactive --dispatch`
- **THEN** the harness SHALL exit with an error: "--interactive and --dispatch are mutually exclusive"

### Requirement: Named lead sessions target their clone
Named leads (non-default) SHALL run against their provisioned git clone rather than the original `--repo` path, providing workspace isolation for independent git operations.

#### Scenario: Named lead session targets clone
- **WHEN** the user runs `harness lead start --repo ./my-repo --name infra --purpose "Infrastructure work"`
- **THEN** the harness SHALL resolve or create the `infra` lead (provisioning a clone if needed), set the working directory to the clone path, and spawn the interactive session against the clone

#### Scenario: Named lead without clone falls back to repo
- **WHEN** a named lead's clone_path is None or the clone directory does not exist
- **THEN** the harness SHALL fall back to running against the original `--repo` path and log a warning

### Requirement: Backward-compatible bare lead command
The bare `harness lead` invocation (without the `start` subcommand) SHALL continue to work identically to the current behavior.

#### Scenario: Bare lead command
- **WHEN** the user runs `harness lead --repo ./my-repo` (no `start` subcommand)
- **THEN** the harness SHALL treat this identically to `harness lead start --repo ./my-repo` — spawning the default lead interactively

