## Context

The repo-lead (`harness lead`) can plan work, triage issues, and dispatch pipeline runs. It works interactively (human-driven) and headless (`--no-interactive --dispatch`). The missing piece is triggering it automatically from external events — GitHub issues, PR events, CI completions.

The operator has a Mac Mini server available for hosting. Cloudflare Tunnel provides HTTPS exposure without port forwarding.

## Goals / Non-Goals

**Goals:**
- Webhook server that receives GitHub events and spawns lead sessions
- Secure (webhook signature verification)
- Per-repo configuration of which events trigger the lead
- Slack notifications for visibility into what the lead is doing
- Deployable on a Mac Mini behind Cloudflare Tunnel

**Non-Goals:**
- Full daemon with health monitoring (Gastown Deacon pattern — future)
- Slack as input (bot that receives commands — future)
- Concurrent lead sessions on the same repo (serial queue per repo)
- Custom event sources beyond GitHub webhooks (future)

## Decisions

### 1. FastAPI + uvicorn for the server

Single POST endpoint (`/webhook`) that receives GitHub events. FastAPI for request parsing and validation, uvicorn as the ASGI server.

```python
@app.post("/webhook")
async def handle_webhook(request: Request):
    verify_signature(request)
    event = parse_github_event(request)
    route_to_lead(event)
```

**Rationale:** FastAPI is lightweight, async-native, and has good typing support. The server is tiny — one endpoint, one handler. No need for a full web framework.

**Alternative considered:** Plain `http.server` from stdlib. Rejected — no async, no signature verification helpers, more boilerplate.

### 2. Serial queue per repo

When a webhook arrives, the server queues a lead session for that repo. Only one lead session runs per repo at a time. If a session is already running, the event is queued and processed when the current session completes.

```
Repo: analytics-monorepo
Queue: [issue #42 (running)] → [issue #43 (waiting)] → [PR #10 merged (waiting)]
```

**Rationale:** Prevents concurrent lead sessions from conflicting — two leads creating proposals for the same repo simultaneously would create chaos. The queue is in-memory (lost on restart, which is acceptable — events will re-trigger on next webhook).

**Alternative considered:** Allow concurrent sessions. Rejected — the lead reads and writes repo state (creates proposals, files issues). Concurrent writes without coordination would conflict.

### 3. Event routing

Map GitHub event types to lead behavior:

| GitHub Event | Lead Prompt | Dispatch? |
|---|---|---|
| `issues.opened` | "Triage new issue #N: {title}. Read the issue body and decide: dispatch directly, create a proposal, or comment asking for clarification." | Yes (if safe) |
| `issues.labeled` (label: `harness`) | Same as opened | Yes |
| `pull_request.closed` (merged) | "PR #{N} was merged for change {label}. Check if any blocked work is now unblocked via `harness ready`." | Yes |
| `check_suite.completed` | "CI completed for branch {branch}. If this is a harness PR waiting for CI, check if auto-merge conditions are met." | No (check only) |

Events not in the routing table are acknowledged (200 OK) but ignored.

**Rationale:** Start with a small set of high-value triggers. More events can be added later without architectural changes.

### 4. Webhook signature verification

GitHub sends an HMAC-SHA256 signature in the `X-Hub-Signature-256` header. The server verifies it against a shared secret configured per-repo (or globally).

```python
def verify_signature(body: bytes, signature: str, secret: str) -> bool:
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)
```

The handler reads `request.body()` and `X-Hub-Signature-256` header, then passes both to `verify_signature`. This keeps the verifier pure (bytes in, bool out) and testable without HTTP fixtures.

**Rationale:** Security requirement — without verification, anyone can POST to the endpoint and trigger lead sessions.

### 5. Per-repo config in `config.yaml`

```yaml
repo_name: analytics-monorepo
remote_url: git@github.com:ActionData/analytics-monorepo.git

webhook:
  enabled: true
  events: [issues.opened, issues.labeled, pull_request.closed]
  auto_dispatch: true
  permission_mode: bypassPermissions

notifications:
  slack_webhook_url: https://hooks.slack.com/services/T.../B.../...
```

Repos without `webhook.enabled: true` ignore incoming webhooks for that repo. The `events` list controls which event types trigger the lead.

**Rationale:** Per-repo control over which events trigger action. Some repos might want full automation, others might want notifications only.

### 6. Slack notifications

Outbound-only Slack integration via webhook URL. The server posts to Slack when:
- A lead session starts ("Triaging issue #42 on analytics-monorepo")
- A lead session completes ("Dispatched harness run for `add-logging` on analytics-monorepo")
- A lead session fails ("Failed to triage issue #42: {error}")

Simple `httpx.post` to the Slack webhook URL with a formatted message block (httpx is available via FastAPI's dependency tree — no additional dependency needed).

**Rationale:** Gives the operator visibility into what the harness is doing without watching logs. Slack is the natural notification channel. Outbound-only avoids the complexity of a Slack bot.

### 7. CLI command: `harness serve`

```
harness serve [--port 8080] [--host 0.0.0.0] [--harness-home PATH]
```

Starts the webhook server. Reads all project `config.yaml` files from `harness_home/projects/` to build the routing table. The server runs until interrupted (Ctrl-C or SIGTERM).

**Rationale:** Consistent with the harness CLI pattern. The serve command is the entry point for always-on operation.

### 8. Deployment: Cloudflare Tunnel

Documented (not code) setup:
1. Install `cloudflared` on the Mac Mini
2. Create a tunnel: `cloudflared tunnel create harness`
3. Route: `cloudflared tunnel route dns harness harness.yourdomain.com`
4. Run: `cloudflared tunnel run harness` (as a launchd service)
5. Configure GitHub webhook to point at `https://harness.yourdomain.com/webhook`

The harness server listens on `localhost:8080`. Cloudflare Tunnel handles HTTPS termination and public exposure.

## Risks / Trade-offs

**[In-memory queue lost on restart]** → Events during server downtime are missed. Mitigation: GitHub retries failed webhook deliveries. The lead's triage is idempotent — re-triaging an issue that was already handled is harmless.

**[Lead sessions are expensive]** → Each lead dispatch is a Claude Code invocation with cost. A burst of issues could trigger many sessions. Mitigation: serial queue limits concurrency. A rate limit (e.g., max 5 sessions per repo per hour) could be added if needed.

**[Mac Mini availability]** → Single server, no redundancy. Mitigation: acceptable for a single-operator system. The harness degrades gracefully — missed webhooks just mean the lead doesn't act until the next event or scheduled triage.

**[Webhook secret management]** → The shared secret must be stored securely. Mitigation: read from environment variable `HARNESS_WEBHOOK_SECRET`, not from config files.

**[bypassPermissions in headless mode]** → Webhook-triggered lead sessions run with `permission_mode: bypassPermissions` by default (configurable per-repo in config.yaml). This is required because Claude Code cannot prompt for permission approval in headless mode. The trade-off is that the lead can perform writes without human approval. Mitigation: the lead's safety model (protected paths, review agents, auto-merge gates) still applies to dispatched pipeline runs. The lead itself can create proposals and file issues — these are low-risk write operations.
