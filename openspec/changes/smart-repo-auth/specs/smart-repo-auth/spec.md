## ADDED Requirements

### Requirement: Detect auth protocol from gh CLI
When `owner/repo` shorthand is used, the harness SHALL check `gh auth status` to determine the configured auth protocol. If HTTPS auth (token) is configured, the HTTPS URL SHALL be used. Otherwise, the SSH URL SHALL be used.

#### Scenario: HTTPS auth configured
- **WHEN** `gh auth status` indicates a token is configured and `--repo user/repo` is used
- **THEN** the clone URL is `https://github.com/user/repo.git`

#### Scenario: No HTTPS auth — SSH default
- **WHEN** `gh auth status` indicates no token and `--repo user/repo` is used
- **THEN** the clone URL is `git@github.com:user/repo.git`

#### Scenario: gh not available
- **WHEN** `gh auth status` fails or gh is not installed
- **THEN** the harness defaults to HTTPS (current behavior)

### Requirement: SSH fallback on HTTPS clone failure
When an HTTPS clone fails, the harness SHALL retry with the SSH equivalent URL before reporting failure.

#### Scenario: HTTPS clone fails, SSH succeeds
- **WHEN** `git clone https://github.com/user/repo.git` fails
- **THEN** the harness retries with `git clone git@github.com:user/repo.git` and succeeds

#### Scenario: Both protocols fail
- **WHEN** both HTTPS and SSH clone attempts fail
- **THEN** the harness reports the SSH error (last attempt) as the failure message

### Requirement: Explicit SSH/HTTPS URLs bypass detection
When a full SSH or HTTPS URL is provided (not shorthand), the harness SHALL use it directly without protocol detection or fallback.

#### Scenario: Explicit SSH URL
- **WHEN** `--repo git@github.com:user/repo.git` is provided
- **THEN** the SSH URL is used directly, no HTTPS detection

#### Scenario: Explicit HTTPS URL
- **WHEN** `--repo https://github.com/user/repo` is provided
- **THEN** the HTTPS URL is used directly, no SSH fallback
