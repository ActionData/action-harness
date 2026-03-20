## ADDED Requirements

### Requirement: tmux availability check
The system SHALL validate that tmux is installed and accessible before attempting any tmux operation. When tmux is not available, the system SHALL raise a clear error message suggesting installation or `--no-detach` as a fallback.

#### Scenario: tmux is installed
- **WHEN** a lead command requires tmux and tmux is available on PATH
- **THEN** the command proceeds normally

#### Scenario: tmux is not installed
- **WHEN** a lead command requires tmux and tmux is not available on PATH
- **THEN** the system SHALL exit with error code 1 and print "tmux is required for persistent lead sessions. Install tmux or use --no-detach for foreground mode."

### Requirement: Create detached tmux session
The system SHALL create a detached tmux session with a named session identifier and execute the Claude Code CLI command inside it. The session name SHALL follow the pattern `harness-lead-{repo_name}-{lead_name}` where repo_name and lead_name are sanitized to contain only alphanumeric characters, dashes, and underscores.

#### Scenario: Create new session
- **WHEN** `create_session()` is called with a session name and command
- **THEN** the system SHALL run `tmux new-session -d -s {session_name} {command}` and return success

#### Scenario: Session name already exists
- **WHEN** `create_session()` is called and a tmux session with that name already exists
- **THEN** the system SHALL raise an error indicating the session already exists

#### Scenario: Session name sanitization
- **WHEN** the repo_name or lead_name contains characters not allowed in tmux session names (dots, slashes, colons)
- **THEN** the system SHALL replace them with dashes to produce a valid tmux session name

### Requirement: Attach to tmux session
The system SHALL attach the current terminal to an existing tmux session, transferring terminal control to the tmux client.

#### Scenario: Attach to running session
- **WHEN** `attach_session()` is called and the named session exists
- **THEN** the system SHALL run `tmux attach-session -t {session_name}` with inherited stdio

#### Scenario: Attach to non-existent session
- **WHEN** `attach_session()` is called and the named session does not exist
- **THEN** the system SHALL raise an error indicating no session found

### Requirement: Kill tmux session
The system SHALL terminate a tmux session by name.

#### Scenario: Kill running session
- **WHEN** `kill_session()` is called and the named session exists
- **THEN** the system SHALL run `tmux kill-session -t {session_name}` and return success

#### Scenario: Kill non-existent session
- **WHEN** `kill_session()` is called and the named session does not exist
- **THEN** the system SHALL return without error (idempotent)

### Requirement: Check session existence
The system SHALL check whether a tmux session with a given name is currently running.

#### Scenario: Session exists
- **WHEN** `has_session()` is called and the named session is running
- **THEN** the system SHALL return True

#### Scenario: Session does not exist
- **WHEN** `has_session()` is called and no session with that name exists
- **THEN** the system SHALL return False

### Requirement: Send keys to tmux session
The system SHALL send keystrokes to a running tmux session for graceful interaction (e.g., sending `/exit` to Claude Code).

#### Scenario: Send exit command
- **WHEN** `send_keys()` is called with text "/exit" and Enter
- **THEN** the system SHALL run `tmux send-keys -t {session_name} "/exit" Enter`

#### Scenario: Send to non-existent session
- **WHEN** `send_keys()` is called and the named session does not exist
- **THEN** the system SHALL raise an error

### Requirement: Get pane PID
The system SHALL retrieve the PID of the process running in a tmux session's active pane.

#### Scenario: Running session
- **WHEN** `session_pane_pid()` is called for an active session
- **THEN** the system SHALL return the integer PID from `tmux display-message -p -t {session_name} '#{pane_pid}'`

#### Scenario: No session
- **WHEN** `session_pane_pid()` is called and the session does not exist
- **THEN** the system SHALL return None
