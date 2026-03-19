"""Shared test fixtures for action-harness tests."""

from collections.abc import Generator
from unittest.mock import patch

import pytest

from action_harness.models import PreflightResult


def _passing_preflight() -> PreflightResult:
    """Return a pre-built passing PreflightResult for mocking."""
    return PreflightResult(
        success=True,
        stage="preflight",
        checks={"worktree_clean": True, "git_remote": True, "eval_tools": True},
        failed_checks=[],
    )


@pytest.fixture
def mock_preflight() -> Generator[None]:
    """Mock preflight to pass — test repos have no remote.

    Use as an explicit fixture in pipeline test files that call
    ``run_pipeline`` with real worktree creation. Preflight behavior
    is tested independently in test_preflight.py.
    """
    with patch("action_harness.pipeline.run_preflight", return_value=_passing_preflight()):
        yield
