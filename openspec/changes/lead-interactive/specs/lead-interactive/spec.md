## ADDED Requirements

### Requirement: Interactive lead session with repo context
The `harness lead --repo <path>` command SHALL spawn an interactive Claude Code session by default, pre-loaded with the lead persona and gathered repo context.

#### Scenario: Default interactive session
- **WHEN** the user runs `harness lead --repo ./my-repo`
- **THEN** the harness SHALL gather repo context, then spawn `claude` (without `-p`) with the lead persona as `--system-prompt` and repo context as `--append-system-prompt`

#### Scenario: Interactive session with initial prompt
- **WHEN** the user runs `harness lead --repo ./my-repo "Focus on test gaps"`
- **THEN** the harness SHALL pass the prompt as a positional argument to `claude` so the session starts with that message

#### Scenario: Interactive session inherits terminal
- **WHEN** an interactive lead session is spawned
- **THEN** the subprocess SHALL inherit stdin, stdout, and stderr so the human can interact naturally with the Claude Code session

### Requirement: Non-interactive mode preserves existing behavior
The `--non-interactive` flag SHALL trigger the existing one-shot dispatch that produces a JSON plan.

#### Scenario: Non-interactive dispatch
- **WHEN** the user runs `harness lead --repo ./my-repo --non-interactive`
- **THEN** the harness SHALL dispatch via `claude -p` and parse the JSON plan output (existing behavior)

#### Scenario: Dispatch requires non-interactive
- **WHEN** the user runs `harness lead --repo ./my-repo --dispatch`
- **THEN** the harness SHALL automatically use non-interactive mode since `--dispatch` requires structured output

### Requirement: Interactive and dispatch are mutually exclusive
The `--interactive` flag and `--dispatch` flag SHALL NOT be used together.

#### Scenario: Explicit interactive with dispatch errors
- **WHEN** the user runs `harness lead --repo ./my-repo --interactive --dispatch`
- **THEN** the harness SHALL exit with an error: "--interactive and --dispatch are mutually exclusive"
