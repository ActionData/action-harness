## 1. Dependencies

- [ ] 1.1 Add `fastapi` and `uvicorn` to `pyproject.toml` dependencies

## 2. Webhook Server Core

- [ ] 2.1 Create `src/action_harness/server.py`. Define `WebhookEvent` dataclass: `repo_full_name: str`, `event_type: str`, `action: str`, `prompt: str`, `auto_dispatch: bool`.
- [ ] 2.2 Add `verify_signature(body: bytes, signature: str, secret: str) -> bool` to `server.py`. Compute `"sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()` and return `hmac.compare_digest(signature, expected)`.
- [ ] 2.3 Create FastAPI app in `server.py` with two endpoints: `POST /webhook` (main handler) and `GET /health` (returns `{"status": "ok"}`). The webhook handler reads `request.body()`, verifies signature via `verify_signature(body, request.headers.get("X-Hub-Signature-256", ""), secret)`. Returns 401 if invalid/missing. Parses JSON body and `X-GitHub-Event` header. Routes to `parse_github_event`.
- [ ] 2.4 Add `parse_github_event(event_type: str, action: str, payload: dict) -> WebhookEvent | None` to `server.py`. Returns `WebhookEvent` for recognized event+action pairs, None for unrecognized. Recognized: `issues.opened`, `issues.labeled`, `pull_request.closed` (only if `payload["pull_request"]["merged"]` is True), `check_suite.completed`.

## 3. Event Routing and Prompt Generation

- [ ] 3.1 In `parse_github_event`, generate prompts per event type: `issues.opened` → `"Triage new issue #{number}: {title}. Read the issue body with gh issue view {number} and decide: dispatch directly (if clear and safe), create an OpenSpec proposal (if it needs design), or comment asking for clarification (if ambiguous)."` with `auto_dispatch=True`. `pull_request.closed` (merged) → `"PR #{number} was merged. Check if any blocked work is now unblocked via harness ready --repo ."` with `auto_dispatch=True`. `check_suite.completed` → `"CI completed for branch {branch}. Check if any harness PRs are waiting for CI to pass."` with `auto_dispatch=False`.
- [ ] 3.2 For `issues.labeled`, extract the label name from `payload["label"]["name"]`. Check against a configurable trigger label (default: `"harness"`). If label does not match, return None. If it matches, generate the same prompt as `issues.opened`.

## 4. Serial Queue

- [ ] 4.1 Add `RepoQueue` class to `server.py` with an `asyncio.Queue` and a background worker task. The worker processes events sequentially: for each event, resolve `harness_agents_dir` via `resolve_harness_agents_dir()` from `action_harness.agents`, call `gather_lead_context(repo_path, harness_home=harness_home)` from `action_harness.lead`, then call `dispatch_lead(repo_path=repo_path, prompt=event.prompt, context=context, harness_agents_dir=harness_agents_dir, permission_mode=config.permission_mode)` from `action_harness.lead`. Run `dispatch_lead` in a thread via `asyncio.to_thread` to avoid blocking the event loop.
- [ ] 4.2 Add `QueueManager` class to `server.py`: holds `dict[str, RepoQueue]` keyed by repo name. `get_or_create(repo_name: str) -> RepoQueue` returns existing or creates new queue with a started worker task. Store on `app.state.queue_manager`.
- [ ] 4.3 In the webhook handler, after parsing the event: look up `WebhookConfig` for the repo, check `enabled` and `events` list, then call `queue_manager.get_or_create(repo_name).enqueue(event)`. Return 200 immediately.

## 5. Per-Repo Config

- [ ] 5.1 Add `WebhookConfig` dataclass to `server.py`: `enabled: bool = False`, `events: list[str] = []`, `auto_dispatch: bool = False`, `permission_mode: str = "bypassPermissions"`, `trigger_label: str = "harness"`, `project_dir: Path`, `slack_webhook_url: str | None = None`.
- [ ] 5.2 Add `load_webhook_configs(harness_home: Path) -> dict[str, WebhookConfig]` to `server.py`. Scan `harness_home / "projects" / */`, read each `config.yaml`, parse the `webhook` and `notifications` sections. Key the dict by `owner/repo` extracted from `remote_url`. Skip projects without `config.yaml` or without `webhook` section.
- [ ] 5.3 Call `load_webhook_configs` on server startup (in a `@app.on_event("startup")` handler). Store on `app.state.webhook_configs`. Also store `harness_home` on `app.state`.
- [ ] 5.4 In the webhook handler, look up `app.state.webhook_configs[repo_full_name]`. If not found or `enabled=False`, return 200 (acknowledged, no action). If event type not in `config.events`, return 200 (no action).

## 6. Slack Notifications

- [ ] 6.1 Create `src/action_harness/notifications.py`. Add `post_slack(webhook_url: str, message: str) -> None`. Use `httpx.post(webhook_url, json={"text": message}, timeout=10)`. Wrap in try/except — log errors to stderr via `typer.echo`, never raise.
- [ ] 6.2 In the `RepoQueue` worker, call `post_slack` at three points: before `dispatch_lead` ("Triaging issue #N on {repo}"), after successful completion ("Lead session completed on {repo}"), on exception ("Lead session failed on {repo}: {error}"). Read `slack_webhook_url` from the event's `WebhookConfig`. Skip if None.

## 7. CLI Command

- [ ] 7.1 Add `serve` command to `cli.py`: `harness serve [--port 8080] [--host 0.0.0.0] [--harness-home PATH]`. Read `HARNESS_WEBHOOK_SECRET` from `os.environ` — if not set, `typer.echo("Error: HARNESS_WEBHOOK_SECRET environment variable is required", err=True)` and exit with code 1. Import the FastAPI app from `server.py`, set `app.state.harness_home` and `app.state.webhook_secret`, then call `uvicorn.run(app, host=host, port=port)`.

## 8. Tests

- [ ] 8.1 Test `verify_signature`: create body `b"test"`, compute expected HMAC with secret `"mysecret"`. Assert `verify_signature(body, expected_sig, "mysecret")` returns True. Assert returns False for wrong signature. Assert returns False for empty signature.
- [ ] 8.2 Test `parse_github_event` for `issues.opened`: payload `{"issue": {"number": 42, "title": "Bug"}}`. Assert returns `WebhookEvent` with prompt containing `"#42"` and `"Bug"` and `auto_dispatch=True`.
- [ ] 8.3 Test `parse_github_event` for `pull_request.closed` with `payload["pull_request"]["merged"] = True`. Assert returns event. Test with `merged = False`. Assert returns None.
- [ ] 8.4 Test `parse_github_event` for `issues.labeled` with matching label `"harness"`. Assert returns event. Test with non-matching label `"bug"`. Assert returns None.
- [ ] 8.5 Test `parse_github_event` for unrecognized event type `"star"`. Assert returns None.
- [ ] 8.6 Test webhook endpoint with FastAPI `TestClient`: POST valid payload with correct signature → assert 200. POST with invalid signature → assert 401. POST with missing signature → assert 401. POST with unrecognized event → assert 204. GET `/health` → assert 200 with `{"status": "ok"}`.
- [ ] 8.7 Test per-repo config filtering: create config with `events: ["issues.opened"]`. Send `check_suite.completed` event. Assert no session queued (mock `dispatch_lead`, assert not called).
- [ ] 8.8 Test `post_slack` with a mock server (or mock `httpx.post`). Assert POST was made with `{"text": "..."}`. Test with exception. Assert no exception propagated.
- [ ] 8.9 Test `HARNESS_WEBHOOK_SECRET` missing: invoke `harness serve` without the env var set. Assert exit code 1 and stderr contains "HARNESS_WEBHOOK_SECRET".

## 9. Documentation

- [ ] 9.1 Create `docs/guides/always-on-setup.md` covering: Cloudflare Tunnel setup (`cloudflared tunnel create`, route, run as launchd service), GitHub webhook configuration (URL, secret, events: Issues + Pull requests + Check suites), Mac Mini launchd plist for `harness serve`, and example project `config.yaml` with webhook + notification settings.

## 10. Self-Validation

- [ ] 10.1 `uv run pytest tests/ -v` — all existing and new tests pass
- [ ] 10.2 `uv run ruff check .` — no lint errors
- [ ] 10.3 `uv run ruff format --check .` — formatting clean
- [ ] 10.4 `uv run mypy src/` — no type errors
- [ ] 10.5 `uv run action-harness serve --help` — shows help with --port, --host, --harness-home options
- [ ] 10.6 Start server with `HARNESS_WEBHOOK_SECRET=test uv run action-harness serve --port 0`, send GET to `/health`, verify 200 response, then shut down
