# named-lead-registry Specification

## Purpose
TBD - created by archiving change named-lead-registry. Update Purpose after archive.
## Requirements
### Requirement: Lead state persistence

The harness SHALL persist lead identity as a `LeadState` Pydantic model serialized to YAML at `$HARNESS_HOME/leads/<repo-name>/<lead-name>/lead.yaml`. The model SHALL include fields: `name` (str), `repo_name` (str), `purpose` (str), `created_at` (str, ISO 8601), `last_active` (str, ISO 8601), `session_id` (str, UUID), `clone_path` (str | None), and `repo_path` (str).

#### Scenario: First start creates lead state
- **WHEN** the user runs `harness lead start --repo /path/to/repo --name ui-bugs --purpose "Track UI regressions"` for the first time
- **THEN** the harness SHALL create `$HARNESS_HOME/leads/<repo-name>/ui-bugs/lead.yaml` containing all LeadState fields, with `created_at` and `last_active` set to the current ISO 8601 timestamp, and `session_id` set to a freshly generated UUID

#### Scenario: Subsequent start updates last_active
- **WHEN** the user starts a lead that already has a `lead.yaml`
- **THEN** the harness SHALL update `last_active` to the current timestamp and preserve all other fields

#### Scenario: Lead state roundtrip
- **WHEN** a `LeadState` is saved to YAML and loaded back
- **THEN** all fields SHALL survive the roundtrip: `name`, `repo_name`, `purpose`, `created_at`, `last_active`, `session_id`, `clone_path`, and `repo_path` SHALL be identical before and after

### Requirement: Repo-name derivation

The harness SHALL derive `<repo-name>` for the leads storage path using a deterministic strategy: (1) if the repo is a managed repo under `$HARNESS_HOME/projects/<name>/repo/`, use `<name>`; (2) otherwise, extract the repo name from `git remote get-url origin` (last path component, stripped of `.git` suffix); (3) if git remote fails, fall back to the directory basename.

#### Scenario: Managed repo uses project name
- **WHEN** the repo path is `$HARNESS_HOME/projects/my-project/repo/`
- **THEN** the derived repo-name SHALL be `my-project`

#### Scenario: Unmanaged repo with git remote
- **WHEN** the repo path is `/home/user/code/my-app` and `git remote get-url origin` returns `git@github.com:org/my-app.git`
- **THEN** the derived repo-name SHALL be `my-app`

#### Scenario: Repo without remote
- **WHEN** the repo path is `/home/user/experiments/prototype` and `git remote get-url origin` fails
- **THEN** the derived repo-name SHALL be `prototype` (the directory basename)

### Requirement: Clone provisioning for named leads

Named leads (non-default) SHALL receive a full git clone at `$HARNESS_HOME/leads/<repo-name>/<lead-name>/clone/`. The clone SHALL be created on first start via `git clone`. The clone source SHALL be the remote URL extracted from the `--repo` path, or the `--repo` path itself if no remote is available.

#### Scenario: First start clones the repo
- **WHEN** the user runs `harness lead start --repo /path/to/repo --name infra` for the first time and the repo has remote `git@github.com:org/repo.git`
- **THEN** the harness SHALL run `git clone git@github.com:org/repo.git $HARNESS_HOME/leads/repo/infra/clone/` and store the clone path in `lead.yaml`

#### Scenario: Subsequent start skips clone
- **WHEN** the user starts a named lead whose `clone_path` already exists on disk
- **THEN** the harness SHALL NOT re-clone; it SHALL use the existing clone directory

#### Scenario: Default lead has no clone
- **WHEN** the user runs `harness lead start --repo /path/to/repo` (no `--name`)
- **THEN** the harness SHALL NOT create a clone; `clone_path` in `lead.yaml` SHALL be `None`; the lead SHALL run against the `--repo` path directly

### Requirement: Session ID management

The harness SHALL control the Claude Code session ID. On first start, it SHALL generate a UUID and pass `--session-id <uuid>` to `claude`. On subsequent starts, it SHALL pass `--resume <session_id>`. If `--resume` fails (non-zero exit), the harness SHALL generate a new UUID, update `session_id` in `lead.yaml`, and fall back to `--session-id <new-uuid>`.

#### Scenario: First start uses --session-id
- **WHEN** a lead starts for the first time (no existing `session_id` in state)
- **THEN** the `claude` command SHALL include `--session-id <generated-uuid>` and the UUID SHALL be persisted in `lead.yaml`

#### Scenario: Subsequent start uses --resume
- **WHEN** a lead starts and has an existing `session_id` in state
- **THEN** the `claude` command SHALL include `--resume <session_id>` instead of `--session-id`

#### Scenario: Failed resume falls back to new session
- **WHEN** `claude --resume <session_id>` exits with a non-zero code
- **THEN** the harness SHALL generate a new UUID, update `lead.yaml`, and re-launch with `--session-id <new-uuid>`, logging the fallback to stderr

### Requirement: Single-instance locking

Each lead SHALL have a lock file at `$HARNESS_HOME/leads/<repo-name>/<lead-name>/lock` containing the PID and session_id. The harness SHALL acquire the lock before starting a session and release it on exit.

#### Scenario: Lock prevents concurrent sessions
- **WHEN** a lead is already running (lock file exists, PID is alive)
- **THEN** attempting to start the same lead SHALL fail with an error message including the lead name and the PID of the running process, and exit code 1

#### Scenario: Stale lock is reclaimed
- **WHEN** a lock file exists but the PID is not alive (process crashed)
- **THEN** the harness SHALL log a warning about the stale lock, reclaim it by overwriting with the new PID, and proceed to start

#### Scenario: Lock is released on normal exit
- **WHEN** a lead session ends normally (claude process exits)
- **THEN** the lock file SHALL be deleted

#### Scenario: Lock is released on exception
- **WHEN** the lead dispatch raises an exception (e.g., TimeoutExpired)
- **THEN** the lock file SHALL still be deleted (via try/finally)

### Requirement: Lead listing

`harness lead list --repo <path>` SHALL display all leads for a repo with their status. For each lead, the output SHALL include: name, purpose, status (active/idle), last active timestamp, and whether the lead has a clone.

#### Scenario: List shows all leads
- **WHEN** the user runs `harness lead list --repo /path/to/repo` and there are leads `default` and `ui-bugs`
- **THEN** the output SHALL list both leads with their name, purpose, status, and last_active timestamp

#### Scenario: Active vs idle status
- **WHEN** a lead has a lock file with a live PID
- **THEN** its status SHALL be `active`
- **WHEN** a lead has no lock file or the lock PID is dead
- **THEN** its status SHALL be `idle`

#### Scenario: List with no leads
- **WHEN** the user runs `harness lead list --repo /path/to/repo` and no leads exist for that repo
- **THEN** the output SHALL state that no leads exist for the repo

### Requirement: Lead retirement

`harness lead retire <name> --repo <path>` SHALL remove a lead by deleting its clone (if present) and its state directory. It SHALL refuse to retire an active (locked) lead.

#### Scenario: Retire removes clone and state
- **WHEN** the user runs `harness lead retire ui-bugs --repo /path/to/repo` and the lead is idle
- **THEN** the harness SHALL delete the clone directory (if it exists), delete the lead state directory (`$HARNESS_HOME/leads/<repo-name>/ui-bugs/`), and confirm the retirement to stderr

#### Scenario: Retire refuses active lead
- **WHEN** the user runs `harness lead retire ui-bugs --repo /path/to/repo` and the lead is active (lock held by a live process)
- **THEN** the harness SHALL exit with an error: "Cannot retire lead 'ui-bugs': currently active (PID <pid>)"

#### Scenario: Retire nonexistent lead
- **WHEN** the user runs `harness lead retire nonexistent --repo /path/to/repo`
- **THEN** the harness SHALL exit with an error: "Lead 'nonexistent' not found for repo <repo-name>"

