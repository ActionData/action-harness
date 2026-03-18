## MODIFIED Requirements

### Requirement: Interactive lead session with repo context
The `harness lead --repo <path>` command SHALL spawn an interactive Claude Code session by default, pre-loaded with the lead persona and gathered repo context. The lead persona SHALL instruct the agent to greet the user with a role explanation, capability overview, and state-aware suggestions.

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
