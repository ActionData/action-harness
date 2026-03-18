"""Tests for webhook server: signature verification, event parsing, endpoints, config."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import yaml
from fastapi.testclient import TestClient

from action_harness.server import (
    WebhookConfig,
    WebhookEvent,
    _extract_owner_repo,
    app,
    load_webhook_configs,
    parse_github_event,
    verify_signature,
)

if TYPE_CHECKING:
    pass

SECRET = "mysecret"


def _sign(body: bytes, secret: str = SECRET) -> str:
    """Compute GitHub-style HMAC-SHA256 signature."""
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _make_test_client(
    configs: dict[str, WebhookConfig] | None = None,
) -> TestClient:
    """Create a TestClient with pre-configured app state."""
    from action_harness.server import QueueManager

    if configs is None:
        configs = {
            "owner/repo": WebhookConfig(
                enabled=True,
                events=["issues.opened", "issues.labeled", "pull_request.closed", "check_suite.completed"],
                auto_dispatch=True,
                project_dir=Path("/tmp/test-project"),
            ),
        }

    app.state.webhook_secret = SECRET
    app.state.harness_home = Path("/tmp/test-harness")
    app.state.webhook_configs = configs
    app.state.queue_manager = QueueManager(configs)
    return TestClient(app, raise_server_exceptions=False)


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
    def test_valid_payload(self) -> None:
        client = _make_test_client()
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

    def test_invalid_signature(self) -> None:
        client = _make_test_client()
        payload = {"action": "opened", "issue": {"number": 1, "title": "X"}, "repository": {"full_name": "owner/repo"}}
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

    def test_missing_signature(self) -> None:
        client = _make_test_client()
        payload = {"action": "opened", "issue": {"number": 1, "title": "X"}, "repository": {"full_name": "owner/repo"}}
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

    def test_unrecognized_event(self) -> None:
        client = _make_test_client()
        payload = {"repository": {"full_name": "owner/repo"}, "action": "created"}
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
        # star.created not in config events, so returns 200 acknowledged
        assert response.status_code == 200

    def test_health_endpoint(self) -> None:
        client = _make_test_client()
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


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

        with patch("action_harness.notifications.httpx.post", side_effect=OSError("network error")):
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
