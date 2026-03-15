## ADDED Requirements

### Requirement: Eval commands run without harness VIRTUAL_ENV
Eval subprocess calls SHALL NOT inherit the harness's `VIRTUAL_ENV` or `VIRTUAL_ENV_PROMPT` environment variables. The target repo's tools SHALL see their own environment.

#### Scenario: VIRTUAL_ENV stripped from eval subprocess
- **WHEN** the harness process has `VIRTUAL_ENV` set AND an eval command runs via `subprocess.run` in the worktree
- **THEN** the subprocess environment does not contain `VIRTUAL_ENV` or `VIRTUAL_ENV_PROMPT`

#### Scenario: Other environment variables preserved
- **WHEN** an eval command runs
- **THEN** all environment variables except `VIRTUAL_ENV` and `VIRTUAL_ENV_PROMPT` are preserved (PATH, HOME, etc.)
