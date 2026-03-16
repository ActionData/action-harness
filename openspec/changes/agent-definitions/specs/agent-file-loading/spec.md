## ADDED Requirements

### Requirement: Agent file format

Agent definition files SHALL be markdown files with optional YAML frontmatter. The frontmatter block is delimited by `---` lines and contains metadata (`name`, `description`). The body after the closing `---` is the agent persona prompt text.

#### Scenario: File with frontmatter
- **WHEN** an agent file contains `---\nname: bug-hunter\ndescription: ...\n---\nYou are a bug-finding specialist...`
- **THEN** `parse_agent_file` returns metadata `{"name": "bug-hunter", "description": "..."}` and body `"You are a bug-finding specialist..."`

#### Scenario: File without frontmatter
- **WHEN** an agent file contains only prompt text with no `---` delimiters
- **THEN** `parse_agent_file` returns empty metadata `{}` and the entire content as the body

#### Scenario: Malformed frontmatter
- **WHEN** an agent file starts with `---` but the YAML between delimiters is invalid
- **THEN** `parse_agent_file` returns empty metadata `{}` and logs a warning

### Requirement: Agent prompt loading with repo override

`load_agent_prompt(agent_name, repo_path, harness_agents_dir)` SHALL load the agent persona from disk. It SHALL check the target repo first (`<repo_path>/.harness/agents/<agent_name>.md`), then fall back to harness defaults (`<harness_agents_dir>/<agent_name>.md`).

#### Scenario: Target repo has override
- **WHEN** `<repo_path>/.harness/agents/bug-hunter.md` exists
- **THEN** the function returns the body from the repo's file, not the harness default

#### Scenario: No repo override, harness default exists
- **WHEN** `<repo_path>/.harness/agents/bug-hunter.md` does not exist and `<harness_agents_dir>/bug-hunter.md` exists
- **THEN** the function returns the body from the harness default file

#### Scenario: No agent file found
- **WHEN** neither the repo override nor the harness default exists for the given agent name
- **THEN** the function raises `FileNotFoundError` with message containing the agent name

### Requirement: Default agent files in harness repo

The harness repo SHALL include default agent definition files at `.harness/agents/`: `bug-hunter.md`, `test-reviewer.md`, `quality-reviewer.md`, `spec-compliance-reviewer.md`, `openspec-reviewer.md`.

#### Scenario: All default agents present
- **WHEN** the harness repo is checked out
- **THEN** `.harness/agents/` contains exactly `bug-hunter.md`, `test-reviewer.md`, `quality-reviewer.md`, `spec-compliance-reviewer.md`, `openspec-reviewer.md`

#### Scenario: Default agent content is richer than current hardcoded prompts
- **WHEN** a default agent file is loaded
- **THEN** it contains at minimum: a persona description, a "What to look for" section, a "How to work" section, and a "Rules" section

### Requirement: Prompt placeholders returned raw

`load_agent_prompt` SHALL return the body text with placeholders (e.g., `{pr_number}`, `{change_name}`) intact. Placeholder formatting is the caller's responsibility, not the loader's.

#### Scenario: Placeholders preserved in loaded prompt
- **WHEN** an agent file body contains `Review PR #{pr_number}`
- **THEN** `load_agent_prompt` returns the string with `{pr_number}` as a literal placeholder, not formatted

### Requirement: Harness agents directory resolution

The harness SHALL resolve its own `.harness/agents/` directory relative to the package installation. When running from source, this is the repo root's `.harness/agents/`. When installed as a package, this uses `importlib.resources` to locate the bundled agent files.

#### Scenario: Running from source
- **WHEN** the harness is invoked from a source checkout
- **THEN** the agents directory resolves to `<repo_root>/.harness/agents/`

#### Scenario: Installed as package
- **WHEN** the harness is installed via `uv pip install` or similar
- **THEN** the agents directory resolves via `importlib.resources` to the bundled `.harness/agents/` files
