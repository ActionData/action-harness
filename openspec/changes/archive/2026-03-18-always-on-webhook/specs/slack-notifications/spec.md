## ADDED Requirements

### Requirement: Slack notification on lead activity

When a lead session starts, completes, or fails, the server SHALL post a notification to the configured Slack webhook URL. Notifications are best-effort — failure to post SHALL NOT fail the lead session.

#### Scenario: Session started notification
- **WHEN** a lead session starts for repo `analytics-monorepo` triggered by issue #42
- **THEN** a Slack message is posted: "Triaging issue #42 on analytics-monorepo"

#### Scenario: Session completed notification
- **WHEN** a lead session completes for repo `analytics-monorepo`
- **THEN** a Slack message is posted containing the repo name and a completion indicator (e.g., "Lead session completed on analytics-monorepo")

#### Scenario: Session failed notification
- **WHEN** a lead session fails with an error
- **THEN** a Slack message is posted: "Lead session failed on analytics-monorepo: {error}"

#### Scenario: Slack webhook not configured
- **WHEN** the repo's `config.yaml` has no `notifications.slack_webhook_url`
- **THEN** no Slack notification is sent and no error is logged

#### Scenario: Slack post fails
- **WHEN** the Slack webhook URL returns an error
- **THEN** the error is logged to stderr but the lead session is not affected

### Requirement: Slack message format

Slack messages SHALL use slack-compatible markup. Messages SHALL include the repo name, event type, and outcome.

#### Scenario: Message content
- **WHEN** a notification is sent for an issue triage
- **THEN** the message contains the repo name, issue number, issue title, and the lead's action (dispatched, proposed, or commented)
