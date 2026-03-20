## ADDED Requirements

### Requirement: Lead start creates tmux session by default
The `harness lead start` command SHALL create a detached tmux session running Claude Code with the lead persona and gathered context, then auto-attach to it. The existing foreground behavior SHALL be available via `--no-detach` flag.

#### Scenario: Default start (tmux)
- **WHEN** user runs `harness lead start --repo .`
- **THEN** the system SHALL create a detached tmux session named `harness-lead-{repo_name}-{lead_name}`, launch Claude Code inside it with the lead persona and context, and attach the terminal to the session

#### Scenario: Start with --no-detach
- **WHEN** user runs `harness lead start --repo . --no-detach`
- **THEN** the system SHALL launch Claude Code as a foreground subprocess (current behavior), without tmux

#### Scenario: Start when session already running
- **WHEN** user runs `harness lead start` and a tmux session for that lead already exists
- **THEN** the system SHALL attach to the existing session instead of creating a new one, and log "Lead session already running, attaching..."

#### Scenario: Start stores tmux session name in state
- **WHEN** a lead is started with tmux
- **THEN** the LeadState SHALL be updated with the `tmux_session` field containing the session name

### Requirement: Lead stop gracefully terminates session
The `harness lead stop` command SHALL gracefully shut down a running lead session by sending `/exit` to Claude Code, waiting for clean shutdown, and then killing the tmux session if still alive.

#### Scenario: Stop a running lead
- **WHEN** user runs `harness lead stop --repo .`
- **THEN** the system SHALL send `/exit` via `tmux send-keys`, wait up to 10 seconds for the process to exit, then kill the tmux session if still running, and release the lock

#### Scenario: Stop when no lead running
- **WHEN** user runs `harness lead stop --repo .` and no lead session exists
- **THEN** the system SHALL print "No active lead session for {repo_name}" and exit with code 0

#### Scenario: Stop named lead
- **WHEN** user runs `harness lead stop --repo . --name infra`
- **THEN** the system SHALL stop the lead session named "infra" for that repo

### Requirement: Lead attach connects to running session
The `harness lead attach` command SHALL connect the current terminal to a running lead's tmux session. If no session is running, it SHALL auto-start one.

#### Scenario: Attach to running lead
- **WHEN** user runs `harness lead attach --repo .` and a lead session is running
- **THEN** the system SHALL attach the terminal to the existing tmux session

#### Scenario: Attach with no running lead (auto-start)
- **WHEN** user runs `harness lead attach --repo .` and no lead session is running
- **THEN** the system SHALL log "No active lead session, starting one...", create a new tmux session, and attach to it

#### Scenario: Attach when tmux session exists but process died
- **WHEN** the tmux session exists but the Claude Code process inside has exited
- **THEN** the system SHALL kill the stale tmux session, create a fresh one, and attach

### Requirement: Lead reset performs clean restart
The `harness lead reset` command SHALL stop any running lead session and start a fresh one with a new session ID.

#### Scenario: Reset running lead
- **WHEN** user runs `harness lead reset --repo .` and a lead is running
- **THEN** the system SHALL stop the existing session (same as `stop`), generate a new session_id, update LeadState, and start a new tmux session

#### Scenario: Reset with no running lead
- **WHEN** user runs `harness lead reset --repo .` and no lead is running
- **THEN** the system SHALL generate a new session_id, update LeadState, and start a new tmux session

### Requirement: Lead status shows session health
The `harness lead status` command SHALL display the current state of lead sessions for a repo, including whether each is running, its tmux session name, and process info.

#### Scenario: Status with running lead
- **WHEN** user runs `harness lead status --repo .` and a lead is active
- **THEN** the system SHALL display the lead name, status "running", tmux session name, and pane PID

#### Scenario: Status with no leads
- **WHEN** user runs `harness lead status --repo .` and no leads exist
- **THEN** the system SHALL print "No lead sessions for {repo_name}"

#### Scenario: Status with stopped lead (state exists, not running)
- **WHEN** a lead has state on disk but no active tmux session
- **THEN** the system SHALL display the lead name with status "stopped" and last_active timestamp

### Requirement: Bare lead command forwards to attach-or-start
The bare `harness lead --repo .` command (no subcommand) SHALL behave as `harness lead attach --repo .`, which auto-starts if needed. This provides the most ergonomic experience for the SSH-attach use case.

#### Scenario: Bare lead with running session
- **WHEN** user runs `harness lead --repo .` and a lead is running
- **THEN** the system SHALL attach to the running session

#### Scenario: Bare lead with no running session
- **WHEN** user runs `harness lead --repo .` and no lead is running
- **THEN** the system SHALL start a new lead session and attach to it

### Requirement: --no-detach flag on start
The `harness lead start` command SHALL accept a `--no-detach` boolean flag that, when set, runs Claude Code as a foreground subprocess without tmux (preserving current behavior).

#### Scenario: Foreground mode
- **WHEN** user runs `harness lead start --repo . --no-detach`
- **THEN** the system SHALL invoke `dispatch_lead_interactive()` directly without tmux, blocking until the session ends

#### Scenario: Default is detached
- **WHEN** user runs `harness lead start --repo .` without `--no-detach`
- **THEN** the system SHALL use tmux detached mode
