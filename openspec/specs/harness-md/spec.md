# harness-md Specification

## Purpose
TBD - created by archiving change harness-md. Update Purpose after archive.
## Requirements
### Requirement: HARNESS.md discovery
The harness SHALL check for a file named `HARNESS.md` in the root of the worktree directory at worker dispatch time.

#### Scenario: HARNESS.md exists
- **WHEN** the worktree contains a `HARNESS.md` file at its root
- **THEN** the harness reads its contents as a UTF-8 string

#### Scenario: HARNESS.md does not exist
- **WHEN** the worktree does not contain a `HARNESS.md` file
- **THEN** the harness proceeds without repo-specific instructions (no error, no warning)

#### Scenario: HARNESS.md is empty
- **WHEN** the worktree contains a `HARNESS.md` file with no content
- **THEN** the harness treats it as absent (no content injected into the system prompt)

### Requirement: HARNESS.md injection into system prompt
The harness SHALL inject the contents of HARNESS.md into the worker's system prompt when the file is present.

#### Scenario: System prompt includes HARNESS.md content
- **WHEN** a HARNESS.md file is discovered with non-empty content
- **THEN** the system prompt passed to the Claude CLI via `--system-prompt` contains the original role instructions followed by a `\n\n## Repo-Specific Instructions\n\n` header and the full HARNESS.md contents

#### Scenario: System prompt unchanged without HARNESS.md
- **WHEN** no HARNESS.md file is present
- **THEN** the system prompt is identical to the current behavior (change name + opsx-apply instructions)

### Requirement: HARNESS.md is freeform markdown
The harness SHALL treat HARNESS.md as opaque markdown content with no required structure or frontmatter.

#### Scenario: Arbitrary markdown content
- **WHEN** HARNESS.md contains any valid markdown (headings, lists, code blocks, plain text)
- **THEN** the harness injects it verbatim without parsing or transformation

#### Scenario: Special characters preserved
- **WHEN** HARNESS.md contains special characters (curly braces, backticks, unicode, template-like syntax)
- **THEN** they are preserved verbatim in the system prompt with no interpolation or escaping

### Requirement: HARNESS.md read from worktree path
The harness SHALL read HARNESS.md from the worktree directory, not the original repo checkout.

#### Scenario: Branch-specific HARNESS.md
- **WHEN** the worktree branch has a different HARNESS.md than the base branch
- **THEN** the worker receives the worktree branch's version

