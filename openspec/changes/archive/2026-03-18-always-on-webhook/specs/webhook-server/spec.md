## ADDED Requirements

### Requirement: Webhook endpoint receives GitHub events

The server SHALL expose a POST endpoint at `/webhook` that accepts GitHub webhook payloads. The endpoint SHALL return 200 OK for recognized events and 204 No Content for unrecognized events.

#### Scenario: Recognized event
- **WHEN** GitHub sends a POST to `/webhook` with event type `issues` and action `opened`
- **THEN** the server returns 200 OK and queues a lead session for the repo

#### Scenario: Unrecognized event
- **WHEN** GitHub sends a POST to `/webhook` with event type `star` (not in routing table)
- **THEN** the server returns 204 No Content and does not queue a session

#### Scenario: Invalid payload
- **WHEN** a POST to `/webhook` contains invalid JSON
- **THEN** the server returns 400 Bad Request

### Requirement: Webhook signature verification

The server SHALL verify the `X-Hub-Signature-256` header against the webhook secret using HMAC-SHA256. Requests with missing or invalid signatures SHALL be rejected with 401 Unauthorized.

#### Scenario: Valid signature
- **WHEN** a request has a valid `X-Hub-Signature-256` header matching the configured secret
- **THEN** the request is processed

#### Scenario: Invalid signature
- **WHEN** a request has an `X-Hub-Signature-256` header that does not match the secret
- **THEN** the server returns 401 Unauthorized and does not queue a session

#### Scenario: Missing signature
- **WHEN** a request has no `X-Hub-Signature-256` header
- **THEN** the server returns 401 Unauthorized

### Requirement: Event routing to lead sessions

The server SHALL map GitHub event types to lead prompts. Supported events: `issues.opened`, `issues.labeled` (with configurable label filter), `pull_request.closed` (merged only), `check_suite.completed`. Each event type generates a specific prompt for the lead agent.

#### Scenario: Issue opened triggers triage
- **WHEN** an `issues.opened` event arrives for repo `analytics-monorepo`
- **THEN** the server spawns `dispatch_lead(repo_path, prompt="Triage new issue #N: {title}...", ...)` with the issue number and title from the payload

#### Scenario: PR merged triggers readiness check
- **WHEN** a `pull_request.closed` event arrives with `merged: true`
- **THEN** the server spawns a lead session with prompt about checking if blocked work is now unblocked

#### Scenario: PR closed without merge is ignored
- **WHEN** a `pull_request.closed` event arrives with `merged: false`
- **THEN** no lead session is queued

#### Scenario: Issue labeled with non-trigger label
- **WHEN** an `issues.labeled` event arrives with label `bug` but the repo's trigger label is `harness`
- **THEN** no lead session is queued

#### Scenario: CI completion triggers check-only session
- **WHEN** a `check_suite.completed` event arrives for a repo
- **THEN** the server spawns a lead session with `auto_dispatch=False` (check and report only, no pipeline dispatch)

### Requirement: Serial queue per repo

The server SHALL maintain an in-memory queue per repo. Only one lead session SHALL run per repo at a time. Additional events for the same repo SHALL be queued and processed sequentially.

#### Scenario: One session at a time
- **WHEN** a lead session is running for `analytics-monorepo` and a new webhook arrives for the same repo
- **THEN** the new event is queued and processed after the current session completes

#### Scenario: Different repos run concurrently
- **WHEN** webhooks arrive simultaneously for `analytics-monorepo` and `action-harness`
- **THEN** lead sessions for both repos start concurrently

#### Scenario: Queue drains on completion
- **WHEN** a lead session completes and the queue has 2 pending events
- **THEN** the next event is dequeued and a new session starts

### Requirement: Per-repo webhook configuration

The server SHALL read `webhook` settings from each project's `config.yaml`. Only repos with `webhook.enabled: true` SHALL accept webhook events. The `events` list controls which event types trigger the lead.

#### Scenario: Webhook disabled for repo
- **WHEN** a webhook arrives for a repo whose `config.yaml` has `webhook.enabled: false` (or no webhook section)
- **THEN** the event is acknowledged (200 OK) but no session is queued

#### Scenario: Event type not in config
- **WHEN** a `check_suite.completed` event arrives but the repo's `webhook.events` list only contains `issues.opened`
- **THEN** the event is acknowledged but no session is queued

### Requirement: CLI serve command

`harness serve` SHALL start the webhook server. It SHALL accept `--port` (default 8080), `--host` (default `0.0.0.0`), and `--harness-home` options. The server SHALL read project configs from `harness_home/projects/` on startup.

#### Scenario: Server starts
- **WHEN** the operator runs `harness serve`
- **THEN** the server starts listening on `0.0.0.0:8080` and logs the startup to stderr

#### Scenario: Custom port
- **WHEN** the operator runs `harness serve --port 9090`
- **THEN** the server listens on port 9090

#### Scenario: Server shutdown
- **WHEN** the operator sends SIGTERM or Ctrl-C
- **THEN** the server shuts down gracefully, completing any in-progress lead session before exiting

### Requirement: Health check endpoint

The server SHALL expose a `GET /health` endpoint that returns 200 OK with `{"status": "ok"}`. This endpoint does not require signature verification.

#### Scenario: Health check
- **WHEN** a GET request is sent to `/health`
- **THEN** the server returns 200 OK with JSON body `{"status": "ok"}`

### Requirement: Webhook secret from environment

The webhook secret SHALL be read from the `HARNESS_WEBHOOK_SECRET` environment variable. If the variable is not set, the server SHALL exit with an error on startup.

#### Scenario: Secret configured
- **WHEN** `HARNESS_WEBHOOK_SECRET` is set
- **THEN** the server starts and uses it for signature verification

#### Scenario: Secret missing
- **WHEN** `HARNESS_WEBHOOK_SECRET` is not set
- **THEN** the server exits with error: "HARNESS_WEBHOOK_SECRET environment variable is required"
