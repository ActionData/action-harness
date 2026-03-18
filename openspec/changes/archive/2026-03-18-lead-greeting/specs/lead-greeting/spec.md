## ADDED Requirements

### Requirement: Greeting explains the lead's role
The lead agent's greeting SHALL include a brief role statement explaining that it is the human's interface to the harness pipeline — the expert on the repo that coordinates implementation, planning, and analysis.

#### Scenario: Role statement in greeting
- **WHEN** the lead agent starts an interactive session without a user prompt
- **THEN** the greeting SHALL include a statement identifying the lead as the repo expert and explaining its relationship to the harness pipeline

### Requirement: Greeting presents capability categories
The lead agent's greeting SHALL surface its key capabilities organized by user intent, covering at minimum: implementing (GitHub issues, OpenSpec changes), planning (exploring ideas, creating proposals), and understanding (answering repo questions, performing analyses).

#### Scenario: Capabilities visible in greeting
- **WHEN** the lead agent generates its initial greeting
- **THEN** the greeting SHALL mention at least three distinct capability categories so the user understands the breadth of what the lead can help with

#### Scenario: Capabilities tied to concrete actions
- **WHEN** the lead presents a capability in the greeting
- **THEN** each capability SHALL reference a specific action the user can take (e.g., "point me at a GitHub issue to implement" rather than "I can help with implementation")

### Requirement: Suggestions reflect repo state
The lead agent's suggested directions SHALL be grounded in the repo's current state — ready changes, open issues, assessment gaps, recent run failures — not generic suggestions.

#### Scenario: Suggestions use context data
- **WHEN** the repo has ready OpenSpec changes, open GitHub issues, or assessment gaps
- **THEN** the suggested directions SHALL reference specific items from the gathered context (e.g., a specific change name, issue number, or low-scoring assessment category)

#### Scenario: Suggestions span capability categories
- **WHEN** the lead generates suggested directions
- **THEN** the suggestions SHALL cover at least two different capability categories (e.g., one implementation suggestion and one exploration suggestion) to demonstrate breadth

### Requirement: Greeting is concise
The lead agent's greeting SHALL be concise enough to fit in a single screen (~20-30 lines) without scrolling, while still covering role, state, capabilities, and suggestions.

#### Scenario: Greeting length
- **WHEN** the lead generates its greeting
- **THEN** the greeting SHALL NOT exceed 30 lines of terminal output
