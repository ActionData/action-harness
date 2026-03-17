## MODIFIED Requirements

### Requirement: Lead command spawns Claude Code session with repo context
The `harness lead --repo <path> "prompt"` command SHALL gather repo context and dispatch a Claude Code session with the repo-lead persona. By default, the session SHALL be interactive. The `--no-interactive` flag SHALL trigger the one-shot JSON dispatch.

#### Scenario: Lead with prompt (interactive default)
- **WHEN** the user runs `harness lead --repo ./my-repo "What should we work on next?"`
- **THEN** the harness SHALL gather context and spawn an interactive Claude Code session with the lead persona and context, using the prompt as the initial message

#### Scenario: Lead with no prompt (interactive default)
- **WHEN** the user runs `harness lead --repo ./my-repo` without a prompt
- **THEN** the harness SHALL spawn an interactive Claude Code session with the lead persona and context, using the default prompt: "Review the repo state and recommend what to work on next"

#### Scenario: Lead non-interactive mode
- **WHEN** the user runs `harness lead --repo ./my-repo --no-interactive "What should we work on next?"`
- **THEN** the harness SHALL gather context and dispatch a one-shot Claude Code session via `claude -p`, parse the JSON plan output, and display the structured plan
