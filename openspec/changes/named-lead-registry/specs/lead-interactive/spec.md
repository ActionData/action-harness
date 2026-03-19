# lead-interactive Specification (Delta)

## MODIFIED Requirements

### Requirement: Interactive lead session with repo context
The `harness lead start --repo <path>` command SHALL spawn an interactive Claude Code session by default, pre-loaded with the lead persona and gathered repo context. The lead persona SHALL instruct the agent to greet the user with a role explanation, capability overview, and state-aware suggestions. When `--name` is provided, the session SHALL target the named lead's clone directory (or the `--repo` path for the default lead). When `--purpose` is provided on first start, it SHALL be stored in the lead's state.

#### Scenario: Default interactive session
- **WHEN** the user runs `harness lead start --repo ./my-repo`
- **THEN** the harness SHALL resolve or create the `default` lead, gather repo context, acquire the lead lock, then spawn `claude` (without `-p`) with the lead persona as `--system-prompt` and repo context as `--append-system-prompt`, using session management (--session-id on first start, --resume on subsequent)

#### Scenario: Named lead session targets clone
- **WHEN** the user runs `harness lead start --repo ./my-repo --name infra --purpose "Infrastructure work"`
- **THEN** the harness SHALL resolve or create the `infra` lead (provisioning a clone if needed), set the working directory to the clone path, and spawn the interactive session against the clone

#### Scenario: Interactive session with initial prompt
- **WHEN** the user runs `harness lead start --repo ./my-repo "Focus on test gaps"`
- **THEN** the harness SHALL pass the prompt as a positional argument to `claude` so the session starts with that message

#### Scenario: Interactive session inherits terminal
- **WHEN** an interactive lead session is spawned
- **THEN** the subprocess SHALL inherit stdin, stdout, and stderr so the human can interact naturally with the Claude Code session

#### Scenario: Greeting includes role and capabilities
- **WHEN** an interactive lead session starts without a user prompt
- **THEN** the lead agent SHALL produce a greeting that explains its role in the harness, lists capability categories, and suggests concrete next steps grounded in repo state

#### Scenario: Backward-compatible bare lead command
- **WHEN** the user runs `harness lead --repo ./my-repo` (no `start` subcommand)
- **THEN** the harness SHALL treat this identically to `harness lead start --repo ./my-repo` — spawning the default lead interactively

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
