## Why

The harness can plan and execute work, but only when a human is at the keyboard. New GitHub issues sit until someone runs `harness lead`. PRs get reviewed only when someone triggers the pipeline. The repo-lead has the judgment to triage issues, create proposals, and dispatch work — but nothing triggers it automatically.

A lightweight webhook server running on a Mac Mini receives GitHub events and spawns lead sessions to react. New issue? The lead triages it. PR merged? The lead checks if blocked work is now unblocked. This is the "always-on" capability — the harness responds to events without human intervention, using the same lead agent and safety model that already exists.

## What Changes

- New `harness serve` command that starts an HTTP server receiving GitHub webhook events
- Webhook signature verification (HMAC-SHA256) for security
- Event routing: map GitHub event types to lead prompts and dispatch modes
- Per-repo webhook configuration in project `config.yaml` (which repos accept webhooks, which events trigger the lead)
- Configurable Slack webhook for notifications (lead posts status updates when it acts)
- Designed for deployment behind Cloudflare Tunnel on a Mac Mini (no port forwarding, HTTPS for free)

## Capabilities

### New Capabilities
- `webhook-server`: HTTP server receiving GitHub webhooks, verifying signatures, routing events to lead sessions
- `slack-notifications`: Outbound Slack webhook integration for posting lead activity updates

### Modified Capabilities
None

## Impact

- New module `src/action_harness/server.py` — FastAPI/uvicorn webhook server
- New module `src/action_harness/notifications.py` — Slack webhook client
- `src/action_harness/cli.py` — new `serve` command
- `pyproject.toml` — add `fastapi` and `uvicorn` dependencies
- Project `config.yaml` gains webhook and notification settings
- Deployment: Cloudflare Tunnel config (documented, not code)

## Prerequisites

Requires `project-consolidation` to be implemented first. The webhook server reads per-repo `config.yaml` from `harness_home/projects/*/config.yaml` — this directory structure and config file convention are created by `project-consolidation`.

This change covers the event-driven portion of the `always-on` roadmap item. Scheduled triage (cron-based lead sessions) can use the same infrastructure but is not part of this scope.
