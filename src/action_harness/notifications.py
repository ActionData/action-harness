"""Outbound notifications: Slack webhook integration."""

from __future__ import annotations

import httpx
import typer


def post_slack(webhook_url: str, message: str) -> None:
    """Post a message to a Slack webhook URL.

    Best-effort: logs errors to stderr but never raises.
    """
    typer.echo(f"[notifications] posting to Slack: {message[:80]}", err=True)
    try:
        response = httpx.post(webhook_url, json={"text": message}, timeout=10)
        typer.echo(
            f"[notifications] Slack response: {response.status_code}",
            err=True,
        )
    except (httpx.HTTPError, OSError) as e:
        typer.echo(f"[notifications] Slack post failed: {e}", err=True)
