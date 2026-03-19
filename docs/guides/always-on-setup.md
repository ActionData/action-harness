# Always-On Webhook Setup

This guide covers deploying the action-harness webhook server on a Mac Mini behind Cloudflare Tunnel, configuring GitHub webhooks, and setting up Slack notifications.

## Prerequisites

- Mac Mini (or any always-on machine) with Python 3.13+ and `uv` installed
- A Cloudflare account with a domain
- GitHub repo(s) you want to monitor
- (Optional) A Slack workspace with an incoming webhook URL

## 1. Cloudflare Tunnel Setup

Cloudflare Tunnel provides HTTPS exposure without port forwarding.

### Install cloudflared

```bash
brew install cloudflare/cloudflare/cloudflared
```

### Create and configure the tunnel

```bash
# Authenticate with Cloudflare
cloudflared tunnel login

# Create a tunnel
cloudflared tunnel create harness

# Route DNS to the tunnel
cloudflared tunnel route dns harness harness.yourdomain.com
```

### Configure the tunnel

Create `~/.cloudflared/config.yml`:

```yaml
tunnel: <your-tunnel-id>
credentials-file: /Users/<you>/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: harness.yourdomain.com
    service: http://localhost:8080
  - service: http_status:404
```

### Run as a launchd service

```bash
cloudflared service install
```

This creates a launchd plist at `~/Library/LaunchAgents/com.cloudflare.cloudflared.plist` that starts the tunnel on login.

To start manually:

```bash
cloudflared tunnel run harness
```

## 2. Harness Server Setup

### Set the webhook secret

Generate a strong secret and set it as an environment variable:

```bash
export HARNESS_WEBHOOK_SECRET=$(openssl rand -hex 32)
echo "Save this secret — you'll need it for GitHub webhook config"
echo "$HARNESS_WEBHOOK_SECRET"
```

### Start the server

```bash
HARNESS_WEBHOOK_SECRET=<your-secret> action-harness serve --port 8080
```

Or with a custom harness home:

```bash
HARNESS_WEBHOOK_SECRET=<your-secret> action-harness serve \
  --port 8080 \
  --harness-home ~/harness
```

### Run as a launchd service

Create `~/Library/LaunchAgents/com.actionharness.serve.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.actionharness.serve</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/YOU/.local/bin/uv</string>
        <string>run</string>
        <string>--project</string>
        <string>/path/to/action-harness</string>
        <string>action-harness</string>
        <string>serve</string>
        <string>--port</string>
        <string>8080</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HARNESS_WEBHOOK_SECRET</key>
        <string>YOUR_SECRET_HERE</string>
        <key>HARNESS_HOME</key>
        <string>/Users/YOU/harness</string>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/Users/YOU/.local/bin</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/actionharness-serve.out.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/actionharness-serve.err.log</string>
</dict>
</plist>
```

Load and start:

```bash
launchctl load ~/Library/LaunchAgents/com.actionharness.serve.plist
```

## 3. GitHub Webhook Configuration

In your GitHub repository (or organization):

1. Go to **Settings → Webhooks → Add webhook**
2. Set:
   - **Payload URL:** `https://harness.yourdomain.com/webhook`
   - **Content type:** `application/json`
   - **Secret:** The same `HARNESS_WEBHOOK_SECRET` value
   - **Events:** Select individual events:
     - ✅ Issues
     - ✅ Pull requests
     - ✅ Check suites
3. Click **Add webhook**

Verify the webhook is working by checking the **Recent Deliveries** tab — the ping event should get a 200 response.

## 4. Project Configuration

Each repo the harness manages needs webhook settings in its `config.yaml`. These files live at `~/harness/projects/<repo-name>/config.yaml`.

### Example config.yaml

```yaml
repo_name: analytics-monorepo
remote_url: git@github.com:YourOrg/analytics-monorepo.git

webhook:
  enabled: true
  events:
    - issues.opened
    - issues.labeled
    - pull_request.closed
    - check_suite.completed
  auto_dispatch: true
  permission_mode: bypassPermissions
  trigger_label: harness

notifications:
  slack_webhook_url: https://hooks.slack.com/services/T.../B.../...
```

### Configuration reference

| Field | Default | Description |
|-------|---------|-------------|
| `webhook.enabled` | `false` | Whether to process webhooks for this repo |
| `webhook.events` | `[]` | List of `event_type.action` strings to handle |
| `webhook.auto_dispatch` | `false` | Whether the lead can auto-dispatch pipeline runs |
| `webhook.permission_mode` | `bypassPermissions` | Claude Code permission mode for lead sessions |
| `webhook.trigger_label` | `harness` | GitHub label that triggers `issues.labeled` events |
| `notifications.slack_webhook_url` | `null` | Slack incoming webhook URL for notifications |

## 5. Slack Notifications Setup

1. In your Slack workspace, go to **Apps → Incoming Webhooks** (or create a Slack app)
2. Create a new webhook for your desired channel
3. Copy the webhook URL
4. Add it to the project's `config.yaml` under `notifications.slack_webhook_url`

The server posts notifications when:
- A lead session starts (e.g., "Triaging issues.opened on owner/repo")
- A lead session completes (e.g., "Lead session completed on owner/repo")
- A lead session fails (e.g., "Lead session failed on owner/repo: error details")

## 6. Verification

### Check the health endpoint

```bash
curl https://harness.yourdomain.com/health
# Expected: {"status":"ok"}
```

### Send a test webhook

```bash
SECRET="your-secret"
BODY='{"action":"opened","issue":{"number":1,"title":"Test"},"repository":{"full_name":"owner/repo"}}'
SIG="sha256=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | cut -d' ' -f2)"

curl -X POST https://harness.yourdomain.com/webhook \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: issues" \
  -H "X-Hub-Signature-256: $SIG" \
  -d "$BODY"
```

### Check logs

```bash
# If running as launchd service
tail -f /tmp/actionharness-serve.err.log
```
