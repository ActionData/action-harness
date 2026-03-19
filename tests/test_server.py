"""Tests for webhook server: signature verification, event parsing, endpoints, config."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml
from fastapi.testclient import TestClient

from action_harness.server import (
    QueueManager,
    WebhookConfig,
    WebhookEvent,
    _extract_owner_repo,
    app,
    load_webhook_configs,
    parse_github_event,
    verify_signature,
)

SECRET = "mysecret"


def _sign(body: bytes, secret: str = SECRET) -> str:
    """Compute GitHub-style HMAC-SHA256 signature."""
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _make_test_client(
    configs: dict[str, WebhookConfig] | None = None,
) -> TestClient:
    """Create a TestClient with pre-configured app state.

    Sets webhook_configs on app.state BEFORE creating the TestClient so that
    the lifespan handler sees it already present and skips config loading.
    This ensures tests run against the provided configs, not an empty dict
    from scanning a nonexistent projects directory.
    """
    if configs is None:
        configs = {
            "owner/repo": WebhookConfig(
                enabled=True,
                events=[
                    "issues.opened",
                    "issues.labeled",
                    "pull_request.closed",
                    "check_suite.completed",
                ],
                auto_dispatch=True,
                project_dir=Path("/tmp/test-project"),
            ),
        }

    # NOTE: Sets shared mutable app.state — each test using _make_test_client
    # must call _cleanup_app_state() in a finally block to avoid cross-test
    # contamination. Acceptable for this module's test count; a fixture-based
    # approach would be warranted if test count grows significantly.
    app.state.webhook_secret = SECRET
    app.state.harness_home = Path("/tmp/test-harness")
    app.state.webhook_configs = configs
    app.state.queue_manager = QueueManager(configs, Path("/tmp/test-harness"))
    return TestClient(app, raise_server_exceptions=False)


def _cleanup_app_state() -> None:
    """Remove webhook_configs from app.state so lifespan runs normally next time."""
    for attr in ("webhook_configs", "queue_manager", "webhook_secret", "harness_home"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)


# ---------------------------------------------------------------------------
# 8.1 — verify_signature
# ---------------------------------------------------------------------------


class TestVerifySignature:
    def test_valid_signature(self) -> None:
        body = b"test"
        sig = _sign(body)
        assert verify_signature(body, sig, SECRET) is True

    def test_invalid_signature(self) -> None:
        body = b"test"
        assert verify_signature(body, "sha256=wrong", SECRET) is False

    def test_empty_signature(self) -> None:
        body = b"test"
        assert verify_signature(body, "", SECRET) is False


# ---------------------------------------------------------------------------
# 8.2 — parse_github_event: issues.opened
# ---------------------------------------------------------------------------


class TestParseIssuesOpened:
    def test_issues_opened(self) -> None:
        payload: dict[str, object] = {
            "action": "opened",
            "issue": {"number": 42, "title": "Bug"},
            "repository": {"full_name": "owner/repo"},
        }
        event = parse_github_event("issues", "opened", payload)
        assert event is not None
        assert isinstance(event, WebhookEvent)
        assert "#42" in event.prompt
        assert "Bug" in event.prompt
        assert event.auto_dispatch is True
        assert event.repo_full_name == "owner/repo"


# ---------------------------------------------------------------------------
# 8.3 — parse_github_event: pull_request.closed
# ---------------------------------------------------------------------------


class TestParsePRClosed:
    def test_merged_pr(self) -> None:
        payload: dict[str, object] = {
            "action": "closed",
            "pull_request": {"number": 10, "merged": True},
            "repository": {"full_name": "owner/repo"},
        }
        event = parse_github_event("pull_request", "closed", payload)
        assert event is not None
        assert "#10" in event.prompt
        assert event.auto_dispatch is True

    def test_unmerged_pr(self) -> None:
        payload: dict[str, object] = {
            "action": "closed",
            "pull_request": {"number": 10, "merged": False},
            "repository": {"full_name": "owner/repo"},
        }
        event = parse_github_event("pull_request", "closed", payload)
        assert event is None


# ---------------------------------------------------------------------------
# 8.4 — parse_github_event: issues.labeled
# ---------------------------------------------------------------------------


class TestParseIssuesLabeled:
    def test_matching_label(self) -> None:
        payload: dict[str, object] = {
            "action": "labeled",
            "label": {"name": "harness"},
            "issue": {"number": 7, "title": "Feature"},
            "repository": {"full_name": "owner/repo"},
        }
        event = parse_github_event("issues", "labeled", payload, trigger_label="harness")
        assert event is not None
        assert "#7" in event.prompt
        assert event.auto_dispatch is True

    def test_non_matching_label(self) -> None:
        payload: dict[str, object] = {
            "action": "labeled",
            "label": {"name": "bug"},
            "issue": {"number": 7, "title": "Feature"},
            "repository": {"full_name": "owner/repo"},
        }
        event = parse_github_event("issues", "labeled", payload, trigger_label="harness")
        assert event is None


# ---------------------------------------------------------------------------
# 8.5 — parse_github_event: unrecognized event
# ---------------------------------------------------------------------------


class TestParseUnrecognized:
    def test_unknown_event(self) -> None:
        payload: dict[str, object] = {
            "repository": {"full_name": "owner/repo"},
        }
        event = parse_github_event("star", "created", payload)
        assert event is None


# ---------------------------------------------------------------------------
# 8.6 — webhook endpoint integration tests
# ---------------------------------------------------------------------------


class TestWebhookEndpoint:
    def test_valid_payload_queued(self) -> None:
        """Valid payload with matching config should be queued (200 + queued)."""
        client = _make_test_client()
        try:
            payload = {
                "action": "opened",
                "issue": {"number": 42, "title": "Bug"},
                "repository": {"full_name": "owner/repo"},
            }
            body = json.dumps(payload).encode()
            response = client.post(
                "/webhook",
                content=body,
                headers={
                    "X-Hub-Signature-256": _sign(body),
                    "X-GitHub-Event": "issues",
                    "Content-Type": "application/json",
                },
            )
            assert response.status_code == 200
            assert response.json()["status"] == "queued"
        finally:
            _cleanup_app_state()

    def test_invalid_signature(self) -> None:
        client = _make_test_client()
        try:
            payload = {
                "action": "opened",
                "issue": {"number": 1, "title": "X"},
                "repository": {"full_name": "owner/repo"},
            }
            body = json.dumps(payload).encode()
            response = client.post(
                "/webhook",
                content=body,
                headers={
                    "X-Hub-Signature-256": "sha256=wrong",
                    "X-GitHub-Event": "issues",
                    "Content-Type": "application/json",
                },
            )
            assert response.status_code == 401
        finally:
            _cleanup_app_state()

    def test_missing_signature(self) -> None:
        client = _make_test_client()
        try:
            payload = {
                "action": "opened",
                "issue": {"number": 1, "title": "X"},
                "repository": {"full_name": "owner/repo"},
            }
            body = json.dumps(payload).encode()
            response = client.post(
                "/webhook",
                content=body,
                headers={
                    "X-GitHub-Event": "issues",
                    "Content-Type": "application/json",
                },
            )
            assert response.status_code == 401
        finally:
            _cleanup_app_state()

    def test_unrecognized_event_returns_204(self) -> None:
        """Event in config's events list but unrecognized by parser → 204."""
        configs = {
            "owner/repo": WebhookConfig(
                enabled=True,
                events=["star.created"],
                project_dir=Path("/tmp/test"),
            ),
        }
        client = _make_test_client(configs)
        try:
            payload = {
                "repository": {"full_name": "owner/repo"},
                "action": "created",
            }
            body = json.dumps(payload).encode()
            response = client.post(
                "/webhook",
                content=body,
                headers={
                    "X-Hub-Signature-256": _sign(body),
                    "X-GitHub-Event": "star",
                    "Content-Type": "application/json",
                },
            )
            assert response.status_code == 204
        finally:
            _cleanup_app_state()

    def test_event_not_in_config_returns_acknowledged(self) -> None:
        """Event not in config's events list → 200 acknowledged."""
        configs = {
            "owner/repo": WebhookConfig(
                enabled=True,
                events=["issues.opened"],
                project_dir=Path("/tmp/test"),
            ),
        }
        client = _make_test_client(configs)
        try:
            payload = {
                "repository": {"full_name": "owner/repo"},
                "action": "created",
            }
            body = json.dumps(payload).encode()
            response = client.post(
                "/webhook",
                content=body,
                headers={
                    "X-Hub-Signature-256": _sign(body),
                    "X-GitHub-Event": "star",
                    "Content-Type": "application/json",
                },
            )
            assert response.status_code == 200
            assert response.json()["action"] == "none"
        finally:
            _cleanup_app_state()

    def test_health_endpoint(self) -> None:
        client = _make_test_client()
        try:
            response = client.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}
        finally:
            _cleanup_app_state()


# ---------------------------------------------------------------------------
# 8.7 — per-repo config filtering
# ---------------------------------------------------------------------------


class TestConfigFiltering:
    def test_event_not_in_config(self) -> None:
        """check_suite.completed not in events list → no session queued."""
        configs = {
            "owner/repo": WebhookConfig(
                enabled=True,
                events=["issues.opened"],
                project_dir=Path("/tmp/test"),
            ),
        }
        client = _make_test_client(configs)
        try:
            payload = {
                "action": "completed",
                "check_suite": {"head_branch": "main"},
                "repository": {"full_name": "owner/repo"},
            }
            body = json.dumps(payload).encode()

            with patch("action_harness.server.QueueManager.get_or_create") as mock_get:
                response = client.post(
                    "/webhook",
                    content=body,
                    headers={
                        "X-Hub-Signature-256": _sign(body),
                        "X-GitHub-Event": "check_suite",
                        "Content-Type": "application/json",
                    },
                )
                assert response.status_code == 200
                mock_get.assert_not_called()
        finally:
            _cleanup_app_state()


# ---------------------------------------------------------------------------
# 8.8 — post_slack
# ---------------------------------------------------------------------------


class TestPostSlack:
    def test_successful_post(self) -> None:
        from action_harness.notifications import post_slack

        with patch("action_harness.notifications.httpx.post") as mock_post:
            mock_post.return_value.status_code = 200
            post_slack("https://hooks.slack.com/test", "Hello")
            mock_post.assert_called_once_with(
                "https://hooks.slack.com/test",
                json={"text": "Hello"},
                timeout=10,
            )

    def test_exception_does_not_propagate(self) -> None:
        from action_harness.notifications import post_slack

        with patch(
            "action_harness.notifications.httpx.post",
            side_effect=OSError("network error"),
        ):
            # Should not raise
            post_slack("https://hooks.slack.com/test", "Hello")


# ---------------------------------------------------------------------------
# 8.9 — HARNESS_WEBHOOK_SECRET missing
# ---------------------------------------------------------------------------


class TestServeSecretRequired:
    def test_missing_secret_exits(self) -> None:
        from typer.testing import CliRunner

        from action_harness.cli import app as cli_app

        runner = CliRunner()
        result = runner.invoke(cli_app, ["serve"], env={"HARNESS_WEBHOOK_SECRET": ""})
        assert result.exit_code == 1
        assert "HARNESS_WEBHOOK_SECRET" in result.output


# ---------------------------------------------------------------------------
# Config loading helpers
# ---------------------------------------------------------------------------


class TestExtractOwnerRepo:
    def test_ssh_url(self) -> None:
        assert _extract_owner_repo("git@github.com:owner/repo.git") == "owner/repo"

    def test_https_url(self) -> None:
        assert _extract_owner_repo("https://github.com/owner/repo.git") == "owner/repo"

    def test_https_no_git_suffix(self) -> None:
        assert _extract_owner_repo("https://github.com/owner/repo") == "owner/repo"

    def test_invalid_url(self) -> None:
        assert _extract_owner_repo("not-a-url") is None


class TestLoadWebhookConfigs:
    def test_loads_from_project_dirs(self, tmp_path: Path) -> None:
        projects_dir = tmp_path / "projects" / "myrepo"
        projects_dir.mkdir(parents=True)
        config = {
            "repo_name": "myrepo",
            "remote_url": "git@github.com:owner/myrepo.git",
            "webhook": {
                "enabled": True,
                "events": ["issues.opened"],
                "trigger_label": "auto",
            },
            "notifications": {
                "slack_webhook_url": "https://hooks.slack.com/test",
            },
        }
        (projects_dir / "config.yaml").write_text(yaml.dump(config))

        result = load_webhook_configs(tmp_path)
        assert "owner/myrepo" in result
        cfg = result["owner/myrepo"]
        assert cfg.enabled is True
        assert cfg.events == ["issues.opened"]
        assert cfg.trigger_label == "auto"
        assert cfg.slack_webhook_url == "https://hooks.slack.com/test"

    def test_skips_missing_webhook_section(self, tmp_path: Path) -> None:
        projects_dir = tmp_path / "projects" / "bare"
        projects_dir.mkdir(parents=True)
        config = {
            "repo_name": "bare",
            "remote_url": "git@github.com:owner/bare.git",
        }
        (projects_dir / "config.yaml").write_text(yaml.dump(config))

        result = load_webhook_configs(tmp_path)
        assert "owner/bare" not in result

    def test_skips_no_remote_url(self, tmp_path: Path) -> None:
        projects_dir = tmp_path / "projects" / "norepo"
        projects_dir.mkdir(parents=True)
        config = {
            "repo_name": "norepo",
            "webhook": {"enabled": True},
        }
        (projects_dir / "config.yaml").write_text(yaml.dump(config))

        result = load_webhook_configs(tmp_path)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Worker dispatch path test (test-reviewer finding)
# ---------------------------------------------------------------------------


class TestRepoQueueWorker:
    # NOTE on patching strategy: _worker uses local imports
    # (from action_harness.lead import ...) so we patch at the source module
    # (action_harness.lead.gather_lead_context). This works because Python's
    # import system caches modules — the local import gets the patched version.
    # This is fragile if action_harness.lead gets imported at the top of this
    # file or via a transitive import before the patch context. Do NOT add
    # top-level imports of action_harness.lead to this test file.

    async def test_worker_dispatches_lead(self) -> None:
        """Worker should call gather_lead_context and dispatch_lead."""
        from action_harness.server import RepoQueue

        configs = {
            "owner/repo": WebhookConfig(
                enabled=True,
                events=["issues.opened"],
                project_dir=Path("/tmp/test-project"),
                slack_webhook_url="https://hooks.slack.com/test",
                permission_mode="bypassPermissions",
            ),
        }

        mock_context = MagicMock()
        mock_context.full_text = "gathered context"

        with (
            patch(
                "action_harness.lead.gather_lead_context",
                return_value=mock_context,
            ) as mock_gather,
            patch(
                "action_harness.lead.dispatch_lead",
                return_value="{}",
            ) as mock_dispatch,
            patch(
                "action_harness.agents.resolve_harness_agents_dir",
                return_value=Path("/tmp/agents"),
            ),
            patch(
                "action_harness.server.post_slack",
            ) as mock_slack,
        ):
            queue = RepoQueue("owner/repo", configs, Path("/tmp/test-harness"))
            queue.start()

            event = WebhookEvent(
                repo_full_name="owner/repo",
                event_type="issues",
                action="opened",
                prompt="Triage issue #1",
                auto_dispatch=True,
            )
            await queue.enqueue(event)
            await asyncio.wait_for(queue._queue.join(), timeout=5)

            # Verify gather_lead_context was called with harness_home
            mock_gather.assert_called_once_with(
                Path("/tmp/test-project/repo"),
                harness_home=Path("/tmp/test-harness"),
            )

            # Verify dispatch_lead was called with correct args
            mock_dispatch.assert_called_once_with(
                repo_path=Path("/tmp/test-project/repo"),
                prompt="Triage issue #1",
                context="gathered context",
                harness_agents_dir=Path("/tmp/agents"),
                permission_mode="bypassPermissions",
            )

            # Verify Slack was called (start + completion)
            assert mock_slack.call_count == 2
            start_msg = mock_slack.call_args_list[0][0][1]
            assert "Triaging" in start_msg
            done_msg = mock_slack.call_args_list[1][0][1]
            assert "completed" in done_msg

    async def test_worker_posts_slack_on_failure(self) -> None:
        """Worker should post Slack failure notification on exception."""
        from action_harness.server import RepoQueue

        configs = {
            "owner/repo": WebhookConfig(
                enabled=True,
                events=["issues.opened"],
                project_dir=Path("/tmp/test-project"),
                slack_webhook_url="https://hooks.slack.com/test",
            ),
        }

        with (
            patch(
                "action_harness.lead.gather_lead_context",
                side_effect=RuntimeError("context error"),
            ),
            patch(
                "action_harness.agents.resolve_harness_agents_dir",
                return_value=Path("/tmp/agents"),
            ),
            patch(
                "action_harness.server.post_slack",
            ) as mock_slack,
        ):
            queue = RepoQueue("owner/repo", configs, Path("/tmp/test-harness"))
            queue.start()

            event = WebhookEvent(
                repo_full_name="owner/repo",
                event_type="issues",
                action="opened",
                prompt="Triage issue #1",
                auto_dispatch=True,
            )
            await queue.enqueue(event)
            await asyncio.wait_for(queue._queue.join(), timeout=5)

            # Verify Slack was called (start + failure)
            assert mock_slack.call_count == 2
            fail_msg = mock_slack.call_args_list[1][0][1]
            assert "failed" in fail_msg
            assert "context error" in fail_msg


# ---------------------------------------------------------------------------
# check_suite.completed event parsing (prior acknowledged finding)
# ---------------------------------------------------------------------------


class TestParseCheckSuiteCompleted:
    def test_check_suite_completed(self) -> None:
        payload: dict[str, object] = {
            "action": "completed",
            "check_suite": {"head_branch": "feature-x"},
            "repository": {"full_name": "owner/repo"},
        }
        event = parse_github_event("check_suite", "completed", payload)
        assert event is not None
        assert "feature-x" in event.prompt
        assert event.auto_dispatch is False
        assert event.event_type == "check_suite"


# ---------------------------------------------------------------------------
# Disabled repo config (prior acknowledged finding)
# ---------------------------------------------------------------------------


class TestDisabledRepoConfig:
    def test_disabled_repo_returns_acknowledged(self) -> None:
        """Repo with enabled=False should return 200 acknowledged, not queue."""
        configs = {
            "owner/repo": WebhookConfig(
                enabled=False,
                events=["issues.opened"],
                project_dir=Path("/tmp/test"),
            ),
        }
        client = _make_test_client(configs)
        try:
            payload = {
                "action": "opened",
                "issue": {"number": 1, "title": "X"},
                "repository": {"full_name": "owner/repo"},
            }
            body = json.dumps(payload).encode()
            response = client.post(
                "/webhook",
                content=body,
                headers={
                    "X-Hub-Signature-256": _sign(body),
                    "X-GitHub-Event": "issues",
                    "Content-Type": "application/json",
                },
            )
            assert response.status_code == 200
            assert response.json()["action"] == "none"
        finally:
            _cleanup_app_state()


# ---------------------------------------------------------------------------
# Invalid JSON payload (prior acknowledged finding)
# ---------------------------------------------------------------------------


class TestInvalidJsonPayload:
    def test_invalid_json_returns_400(self) -> None:
        client = _make_test_client()
        try:
            body = b"not valid json"
            response = client.post(
                "/webhook",
                content=body,
                headers={
                    "X-Hub-Signature-256": _sign(body),
                    "X-GitHub-Event": "issues",
                    "Content-Type": "application/json",
                },
            )
            assert response.status_code == 400
        finally:
            _cleanup_app_state()


# ---------------------------------------------------------------------------
# post_slack with HTTP error status (prior acknowledged finding)
# ---------------------------------------------------------------------------


class TestPostSlackHttpError:
    def test_http_error_status_does_not_propagate(self) -> None:
        from action_harness.notifications import post_slack

        with patch("action_harness.notifications.httpx.post") as mock_post:
            mock_post.return_value.status_code = 500
            # Should not raise — best-effort
            post_slack("https://hooks.slack.com/test", "Hello")
