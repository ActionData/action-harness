## Why

Named leads with memory can accumulate expertise, but they can't receive messages from other agents or external events. When a webhook event arrives that's relevant to a specific lead, there's no way to route it there. When the default lead triages an issue and decides "this belongs to the ui-bugs lead," it has no mechanism to hand it off.

## What Changes

- Per-lead inbox.md for receiving messages (append-only until cleared)
- inbox-archive/ for processed message history
- auto_wake config in lead.yaml — when true, incoming messages auto-start the lead
- Slack notification when messages arrive for leads with auto_wake=false
- Skills: /action:inbox-check, /action:inbox-clear, /action:inbox-send, /action:inbox-history
- CLI: `harness inbox send <lead> <message> --repo .`
- PostCompact hook extended to re-inject pending inbox alongside memory

## Prerequisites

Requires `named-lead-registry`. Benefits from `lead-memory` (shared PostCompact hook).

*Stub proposal — full design to be written after phases 1a and 1b are implemented.*
