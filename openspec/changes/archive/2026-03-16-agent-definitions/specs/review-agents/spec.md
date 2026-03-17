## MODIFIED Requirements

### Requirement: Agent System Prompts

Each review agent SHALL use a system prompt loaded from `.harness/agents/<agent_name>.md` (target repo override or harness default). The persona text from the file is combined with the harness's JSON output format suffix at dispatch time. The user prompt SHALL include the PR number. The `{pr_number}` placeholder in the loaded prompt SHALL be formatted before dispatch.

#### Scenario: Review agent prompt loaded from file
- **WHEN** the bug-hunter agent is dispatched
- **THEN** its system prompt is the body of `bug-hunter.md` (from repo override or harness default) concatenated with the JSON output format suffix

#### Scenario: Agent prompt includes PR number
- **WHEN** any review agent is dispatched for PR #42
- **THEN** its user prompt includes the PR number so the agent can run `gh pr diff 42`

#### Scenario: Output format appended by harness
- **WHEN** any review agent prompt is constructed
- **THEN** the JSON output format block (findings schema, severity definitions) is appended after the persona text from the file

#### Scenario: Repo override takes precedence
- **WHEN** the target repo has `.harness/agents/quality-reviewer.md`
- **THEN** the quality-reviewer uses the repo's prompt instead of the harness default
