## Why

With named leads and an inbox system, the missing piece is connecting GitHub webhook events to the right lead. Today the webhook server (from `always-on-webhook`) dispatches all events to a single default lead. But if you have a "ui-bugs" lead that's an expert on the frontend, UI-related issues should reach it directly instead of being manually triaged.

## What Changes

- Default lead remains the catch-all for unrouted events
- Default lead can triage and route via /action:inbox-send to named leads
- Optional direct routing config in project config.yaml (event type + label → named lead)
- Auto-wake integration: routed messages trigger lead startup when auto_wake=true

## Prerequisites

Requires `lead-inbox` and `always-on-webhook`.

*Stub proposal — full design to be written after inbox system is implemented and the default-lead triage pattern is validated.*
