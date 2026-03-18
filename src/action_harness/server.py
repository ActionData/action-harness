"""Webhook server: receives GitHub events and dispatches lead sessions."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

import typer
import yaml
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from action_harness.notifications import post_slack

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class WebhookEvent:
    """A parsed GitHub webhook event ready for dispatch."""

    repo_full_name: str
    event_type: str
    action: str
    prompt: str
    # NOTE: auto_dispatch is set per event type but not yet consumed by the
    # queue worker — it will gate whether dispatch_lead is called vs. a
    # check-only session when that distinction is implemented.
    auto_dispatch: bool


@dataclass
class WebhookConfig:
    """Per-repo webhook configuration from config.yaml."""

    enabled: bool = False
    events: list[str] = field(default_factory=list)
    auto_dispatch: bool = False
    permission_mode: str = "bypassPermissions"
    trigger_label: str = "harness"
    project_dir: Path = field(default_factory=lambda: Path("."))
    slack_webhook_url: str | None = None


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------


def verify_signature(body: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature.

    Returns True if the signature matches, False otherwise.
    """
    if not signature:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


# ---------------------------------------------------------------------------
# Event parsing and prompt generation
# ---------------------------------------------------------------------------


def _extract_repo_full_name(payload: dict[str, object]) -> str:
    """Extract owner/repo from the payload's repository field."""
    repo = payload.get("repository")
    if isinstance(repo, dict):
        full_name = repo.get("full_name")
        if isinstance(full_name, str):
            return full_name
    return ""


def parse_github_event(
    event_type: str,
    action: str,
    payload: dict[str, object],
    trigger_label: str = "harness",
) -> WebhookEvent | None:
    """Parse a GitHub webhook event into a WebhookEvent, or None if unrecognized.

    Recognized event+action pairs:
    - issues.opened
    - issues.labeled (with matching trigger label)
    - pull_request.closed (only if merged)
    - check_suite.completed
    """
    repo_full_name = _extract_repo_full_name(payload)

    if event_type == "issues" and action == "opened":
        issue = payload.get("issue", {})
        if not isinstance(issue, dict):
            return None
        number = issue.get("number", 0)
        title = issue.get("title", "")
        prompt = (
            f"Triage new issue #{number}: {title}. "
            f"Read the issue body with gh issue view {number} and decide: "
            "dispatch directly (if clear and safe), create an OpenSpec proposal "
            "(if it needs design), or comment asking for clarification (if ambiguous)."
        )
        return WebhookEvent(
            repo_full_name=repo_full_name,
            event_type="issues",
            action="opened",
            prompt=prompt,
            auto_dispatch=True,
        )

    if event_type == "issues" and action == "labeled":
        label = payload.get("label", {})
        if not isinstance(label, dict):
            return None
        label_name = label.get("name", "")
        if label_name != trigger_label:
            return None
        issue = payload.get("issue", {})
        if not isinstance(issue, dict):
            return None
        number = issue.get("number", 0)
        title = issue.get("title", "")
        prompt = (
            f"Triage new issue #{number}: {title}. "
            f"Read the issue body with gh issue view {number} and decide: "
            "dispatch directly (if clear and safe), create an OpenSpec proposal "
            "(if it needs design), or comment asking for clarification (if ambiguous)."
        )
        return WebhookEvent(
            repo_full_name=repo_full_name,
            event_type="issues",
            action="labeled",
            prompt=prompt,
            auto_dispatch=True,
        )

    if event_type == "pull_request" and action == "closed":
        pr = payload.get("pull_request", {})
        if not isinstance(pr, dict):
            return None
        if not pr.get("merged"):
            return None
        number = pr.get("number", 0)
        prompt = (
            f"PR #{number} was merged. "
            "Check if any blocked work is now unblocked via harness ready --repo ."
        )
        return WebhookEvent(
            repo_full_name=repo_full_name,
            event_type="pull_request",
            action="closed",
            prompt=prompt,
            auto_dispatch=True,
        )

    if event_type == "check_suite" and action == "completed":
        head_branch = ""
        check_suite = payload.get("check_suite", {})
        if isinstance(check_suite, dict):
            branch_val = check_suite.get("head_branch", "")
            if isinstance(branch_val, str):
                head_branch = branch_val
        prompt = (
            f"CI completed for branch {head_branch}. "
            "Check if any harness PRs are waiting for CI to pass."
        )
        return WebhookEvent(
            repo_full_name=repo_full_name,
            event_type="check_suite",
            action="completed",
            prompt=prompt,
            auto_dispatch=False,
        )

    return None


# ---------------------------------------------------------------------------
# Per-repo config loading
# ---------------------------------------------------------------------------


def _extract_owner_repo(remote_url: str) -> str | None:
    """Extract owner/repo from a git remote URL.

    Handles both SSH (git@github.com:owner/repo.git) and HTTPS
    (https://github.com/owner/repo.git) formats.
    """
    # SSH format: git@github.com:owner/repo.git
    ssh_match = re.match(r"git@[^:]+:(.+?)(?:\.git)?$", remote_url)
    if ssh_match:
        return ssh_match.group(1)
    # HTTPS format: https://github.com/owner/repo.git
    https_match = re.match(r"https?://[^/]+/(.+?)(?:\.git)?$", remote_url)
    if https_match:
        return https_match.group(1)
    return None


def load_webhook_configs(harness_home: Path) -> dict[str, WebhookConfig]:
    """Load webhook configs from all projects in harness_home.

    Scans harness_home/projects/*/, reads each config.yaml, and extracts
    webhook and notification settings. Keys the dict by owner/repo.
    """
    typer.echo(f"[server] loading webhook configs from {harness_home}", err=True)
    configs: dict[str, WebhookConfig] = {}
    projects_dir = harness_home / "projects"
    if not projects_dir.is_dir():
        typer.echo(f"[server] no projects directory at {projects_dir}", err=True)
        return configs

    for entry in sorted(projects_dir.iterdir()):
        if not entry.is_dir():
            continue
        config_path = entry / "config.yaml"
        if not config_path.is_file():
            continue

        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as e:
            typer.echo(f"[server] failed to read {config_path}: {e}", err=True)
            continue

        if not isinstance(raw, dict):
            continue

        # Extract owner/repo from remote_url
        remote_url = raw.get("remote_url", "")
        if not isinstance(remote_url, str) or not remote_url:
            continue
        owner_repo = _extract_owner_repo(remote_url)
        if owner_repo is None:
            typer.echo(f"[server] could not extract owner/repo from {remote_url}", err=True)
            continue

        # Parse webhook section — skip projects without it
        webhook_raw = raw.get("webhook")
        if not isinstance(webhook_raw, dict):
            continue

        # Parse notifications section
        notifications_raw = raw.get("notifications", {})
        if not isinstance(notifications_raw, dict):
            notifications_raw = {}

        raw_events = webhook_raw.get("events", [])
        events: list[str] = []
        if isinstance(raw_events, list):
            for ev in raw_events:
                if isinstance(ev, str):
                    events.append(ev)

        raw_enabled = webhook_raw.get("enabled", False)
        raw_auto = webhook_raw.get("auto_dispatch", False)
        raw_perm = webhook_raw.get("permission_mode", "bypassPermissions")
        raw_label = webhook_raw.get("trigger_label", "harness")
        raw_slack = notifications_raw.get("slack_webhook_url")

        config = WebhookConfig(
            enabled=bool(raw_enabled),
            events=events,
            auto_dispatch=bool(raw_auto),
            permission_mode=str(raw_perm),
            trigger_label=str(raw_label),
            project_dir=entry,
            slack_webhook_url=str(raw_slack) if raw_slack else None,
        )
        configs[owner_repo] = config
        typer.echo(
            f"[server] loaded config for {owner_repo}: enabled={config.enabled}, "
            f"events={config.events}",
            err=True,
        )

    typer.echo(f"[server] loaded {len(configs)} webhook config(s)", err=True)
    return configs


# ---------------------------------------------------------------------------
# Serial queue per repo
# ---------------------------------------------------------------------------


_MAX_WORKER_RESTARTS = 5
_RESTART_BACKOFF_BASE_SECONDS = 1.0


class RepoQueue:
    """In-memory serial queue for a single repo's webhook events."""

    def __init__(
        self,
        repo_name: str,
        configs: dict[str, WebhookConfig],
        harness_home: Path,
    ) -> None:
        self.repo_name = repo_name
        self._queue: asyncio.Queue[WebhookEvent] = asyncio.Queue()
        self._configs = configs
        self._harness_home = harness_home
        self._task: asyncio.Task[None] | None = None
        self._restart_count = 0

    def start(self) -> None:
        """Start the background worker task."""
        self._task = asyncio.create_task(self._worker())
        self._task.add_done_callback(self._on_worker_done)

    def _on_worker_done(self, task: asyncio.Task[None]) -> None:
        """Log and restart with exponential backoff if the worker dies.

        Caps restarts at _MAX_WORKER_RESTARTS to prevent infinite spin
        loops when the failure is persistent (e.g., broken import).
        """
        exc = task.exception() if not task.cancelled() else None
        if exc is not None:
            self._restart_count += 1
            if self._restart_count > _MAX_WORKER_RESTARTS:
                typer.echo(
                    f"[server] worker for {self.repo_name} died {self._restart_count} "
                    f"times; giving up. Last error: {exc}",
                    err=True,
                )
                return
            delay = _RESTART_BACKOFF_BASE_SECONDS * (2 ** (self._restart_count - 1))
            typer.echo(
                f"[server] worker for {self.repo_name} died: {exc}; "
                f"restarting in {delay:.0f}s (attempt {self._restart_count}/"
                f"{_MAX_WORKER_RESTARTS})",
                err=True,
            )
            loop = asyncio.get_running_loop()
            loop.call_later(delay, self.start)
        elif task.cancelled():
            typer.echo(
                f"[server] worker for {self.repo_name} was cancelled",
                err=True,
            )

    async def enqueue(self, event: WebhookEvent) -> None:
        """Add an event to the queue."""
        await self._queue.put(event)
        typer.echo(
            f"[server] enqueued {event.event_type}.{event.action} for {self.repo_name}",
            err=True,
        )

    async def _worker(self) -> None:
        """Process events sequentially."""
        while True:
            event = await self._queue.get()
            config = self._configs.get(self.repo_name)
            slack_url = config.slack_webhook_url if config else None
            permission_mode = config.permission_mode if config else "bypassPermissions"

            typer.echo(
                f"[server] processing {event.event_type}.{event.action} for {self.repo_name}",
                err=True,
            )

            # NOTE: Slack message omits issue number — the event prompt has it,
            # but extracting it here would require parsing. Acceptable for v1.
            if slack_url:
                await asyncio.to_thread(
                    post_slack,
                    slack_url,
                    f"Triaging {event.event_type}.{event.action} on {self.repo_name}",
                )

            try:
                # Import here to avoid circular imports and to keep the module
                # importable without all lead dependencies in test contexts
                from action_harness.agents import resolve_harness_agents_dir
                from action_harness.lead import dispatch_lead, gather_lead_context

                harness_agents_dir = resolve_harness_agents_dir()
                project_dir = config.project_dir if config else Path(".")
                repo_path = project_dir / "repo"

                context = gather_lead_context(repo_path, harness_home=self._harness_home)
                await asyncio.to_thread(
                    dispatch_lead,
                    repo_path=repo_path,
                    prompt=event.prompt,
                    context=context.full_text,
                    harness_agents_dir=harness_agents_dir,
                    permission_mode=permission_mode,
                )

                # Reset restart counter — worker is healthy after a successful event
                self._restart_count = 0

                typer.echo(
                    f"[server] completed {event.event_type}.{event.action} for {self.repo_name}",
                    err=True,
                )
                if slack_url:
                    await asyncio.to_thread(
                        post_slack,
                        slack_url,
                        f"Lead session completed on {self.repo_name}",
                    )
            except Exception as exc:
                typer.echo(
                    f"[server] failed {event.event_type}.{event.action} "
                    f"for {self.repo_name}: {exc}",
                    err=True,
                )
                if slack_url:
                    await asyncio.to_thread(
                        post_slack,
                        slack_url,
                        f"Lead session failed on {self.repo_name}: {exc}",
                    )
            finally:
                self._queue.task_done()


class QueueManager:
    """Manages per-repo queues."""

    def __init__(self, configs: dict[str, WebhookConfig], harness_home: Path) -> None:
        self._queues: dict[str, RepoQueue] = {}
        self._configs = configs
        self._harness_home = harness_home

    def get_or_create(self, repo_name: str) -> RepoQueue:
        """Get existing queue or create a new one with a started worker."""
        if repo_name not in self._queues:
            queue = RepoQueue(repo_name, self._configs, self._harness_home)
            queue.start()
            self._queues[repo_name] = queue
        return self._queues[repo_name]


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Load webhook configs on startup.

    Skipped when app.state.webhook_configs is already set (e.g., in tests
    that configure state before creating the TestClient).

    NOTE: No graceful shutdown of worker tasks or subprocesses on exit.
    Worker tasks are fire-and-forget asyncio tasks; uvicorn's SIGTERM
    handling cancels them. In-flight dispatch_lead subprocesses may be
    orphaned — acceptable for v1 since the lead is idempotent.
    """
    if not hasattr(application.state, "webhook_configs"):
        harness_home: Path = application.state.harness_home
        configs = load_webhook_configs(harness_home)
        application.state.webhook_configs = configs
        application.state.queue_manager = QueueManager(configs, harness_home)
        typer.echo(
            f"[server] started with {len(configs)} repo config(s)",
            err=True,
        )
    yield


app = FastAPI(title="action-harness webhook server", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/webhook")
async def handle_webhook(request: Request) -> JSONResponse:
    """Handle incoming GitHub webhook events."""
    webhook_secret: str = request.app.state.webhook_secret
    webhook_configs: dict[str, WebhookConfig] = request.app.state.webhook_configs
    queue_manager: QueueManager = request.app.state.queue_manager

    # Read and verify signature
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    if not verify_signature(body, signature, webhook_secret):
        typer.echo("[server] webhook signature verification failed", err=True)
        return JSONResponse(status_code=401, content={"error": "Invalid signature"})

    # Parse event
    event_type = request.headers.get("X-GitHub-Event", "")
    try:
        payload: dict[str, object] = json.loads(body)
    except (json.JSONDecodeError, ValueError) as e:
        typer.echo(f"[server] invalid JSON payload: {e}", err=True)
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    action = ""
    raw_action = payload.get("action")
    if isinstance(raw_action, str):
        action = raw_action

    repo_full_name = _extract_repo_full_name(payload)

    # Check per-repo config
    config = webhook_configs.get(repo_full_name)
    if config is None or not config.enabled:
        typer.echo(
            f"[server] no enabled config for {repo_full_name}, acknowledging",
            err=True,
        )
        return JSONResponse(status_code=200, content={"status": "acknowledged", "action": "none"})

    # Check if event type is in the config's events list
    event_key = f"{event_type}.{action}" if action else event_type
    if not _event_matches(event_key, config.events):
        typer.echo(
            f"[server] event {event_key} not in config for {repo_full_name}, skipping",
            err=True,
        )
        return JSONResponse(status_code=200, content={"status": "acknowledged", "action": "none"})

    # Parse the event
    event = parse_github_event(event_type, action, payload, config.trigger_label)
    if event is None:
        typer.echo(
            f"[server] unrecognized event {event_type}.{action}, returning 204",
            err=True,
        )
        return JSONResponse(status_code=204, content=None)

    # Enqueue for processing
    queue = queue_manager.get_or_create(repo_full_name)
    await queue.enqueue(event)

    typer.echo(
        f"[server] queued {event_type}.{action} for {repo_full_name}",
        err=True,
    )
    return JSONResponse(status_code=200, content={"status": "queued"})


def _event_matches(event_key: str, allowed_events: Sequence[str]) -> bool:
    """Check if an event key matches any of the allowed events.

    Exact match only — wildcard/prefix matching (e.g., "issues.*") is not
    supported. Config must list each event.action pair explicitly. This is
    intentional: explicit config prevents accidental dispatch on unexpected
    event subtypes.
    """
    return event_key in allowed_events
