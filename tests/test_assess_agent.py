"""Tests for assessment agent dispatch and merging."""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from action_harness.assess_agent import (
    build_system_prompt,
    build_user_prompt,
    dispatch_readonly_worker,
    merge_agent_results,
    run_agent_assessment,
)
from action_harness.assessment import (
    CategoryScore,
    CIMechanicalSignals,
    ContextMechanicalSignals,
    IsolationMechanicalSignals,
    ObservabilityMechanicalSignals,
    TestabilityMechanicalSignals,
    ToolingMechanicalSignals,
)


def _make_categories() -> dict[str, CategoryScore]:
    """Create a sample categories dict."""
    return {
        "ci_guardrails": CategoryScore(
            score=60,
            mechanical_signals=CIMechanicalSignals(ci_exists=True, runs_tests=True),
        ),
        "testability": CategoryScore(
            score=40,
            mechanical_signals=TestabilityMechanicalSignals(test_files=3),
        ),
        "context": CategoryScore(
            score=50,
            mechanical_signals=ContextMechanicalSignals(claude_md=True),
        ),
        "tooling": CategoryScore(
            score=60,
            mechanical_signals=ToolingMechanicalSignals(package_manager=True),
        ),
        "observability": CategoryScore(
            score=30,
            mechanical_signals=ObservabilityMechanicalSignals(),
        ),
        "isolation": CategoryScore(
            score=80,
            mechanical_signals=IsolationMechanicalSignals(git_repo=True),
        ),
    }


def test_system_prompt_contains_schema() -> None:
    """System prompt includes expected JSON output schema."""
    prompt = build_system_prompt()
    assert "score_adjustment" in prompt
    assert "rationale" in prompt
    assert "gaps" in prompt
    assert "categories" in prompt


def test_user_prompt_contains_signals() -> None:
    """User prompt includes mechanical signals JSON."""
    signals = {
        "ci_guardrails": {"score": 60, "signals": {"ci_exists": True}},
    }
    prompt = build_user_prompt(signals)
    assert "ci_guardrails" in prompt
    assert "ci_exists" in prompt


def test_merge_agent_results_basic() -> None:
    """Agent results merge correctly with mechanical scores."""
    categories = _make_categories()
    agent_results = {
        "categories": {
            "ci_guardrails": {
                "score_adjustment": 10,
                "rationale": "CI tests are comprehensive",
                "gaps": [],
            },
            "testability": {
                "score_adjustment": -5,
                "rationale": "Tests lack assertions",
                "gaps": [
                    {
                        "severity": "medium",
                        "finding": "Tests have weak assertions",
                        "proposal_name": "improve-test-assertions",
                    }
                ],
            },
        }
    }

    merged = merge_agent_results(categories, agent_results)

    # CI score adjusted up by 10
    assert merged["ci_guardrails"].score == 70
    assert merged["ci_guardrails"].agent_assessment == "CI tests are comprehensive"

    # Testability adjusted down by 5
    assert merged["testability"].score == 35
    assert len(merged["testability"].gaps) == 1
    assert merged["testability"].gaps[0].proposal_name == "improve-test-assertions"


def test_merge_agent_score_clamped() -> None:
    """Agent adjustment > 20 gets clamped to 20."""
    categories = _make_categories()
    agent_results = {
        "categories": {
            "ci_guardrails": {
                "score_adjustment": 50,  # should be clamped to +20
                "rationale": "Over-enthusiastic",
                "gaps": [],
            },
            "context": {
                "score_adjustment": -30,  # should be clamped to -20
                "rationale": "Harsh assessment",
                "gaps": [],
            },
        }
    }

    merged = merge_agent_results(categories, agent_results)

    # 60 + 20 (clamped from 50)
    assert merged["ci_guardrails"].score == 80

    # 50 - 20 (clamped from -30)
    assert merged["context"].score == 30


def test_merge_agent_failure_fallback() -> None:
    """Missing categories key falls back gracefully."""
    categories = _make_categories()
    agent_results = {"error": "something went wrong"}

    merged = merge_agent_results(categories, agent_results)

    # Scores unchanged
    assert merged["ci_guardrails"].score == 60
    assert merged["testability"].score == 40


def test_merge_preserves_mechanical_gaps() -> None:
    """Agent gaps are appended to existing mechanical gaps, not replacing."""
    from action_harness.assessment import Gap

    categories = _make_categories()
    categories["ci_guardrails"].gaps = [
        Gap(severity="high", finding="Existing gap", category="ci_guardrails")
    ]

    agent_results = {
        "categories": {
            "ci_guardrails": {
                "score_adjustment": 0,
                "rationale": "OK",
                "gaps": [{"severity": "low", "finding": "Agent gap", "proposal_name": None}],
            }
        }
    }

    merged = merge_agent_results(categories, agent_results)
    assert len(merged["ci_guardrails"].gaps) == 2
    assert merged["ci_guardrails"].gaps[0].finding == "Existing gap"
    assert merged["ci_guardrails"].gaps[1].finding == "Agent gap"


def test_user_prompt_valid_json() -> None:
    """The mechanical signals in the user prompt are valid JSON."""
    signals = {
        "ci_guardrails": {"score": 60, "signals": {"ci_exists": True, "runs_tests": True}},
        "testability": {"score": 40, "signals": {"test_files": 3}},
    }
    prompt = build_user_prompt(signals)

    # Extract JSON from prompt
    json_start = prompt.find("{")
    json_end = prompt.rfind("}") + 1
    parsed = json.loads(prompt[json_start:json_end])
    assert parsed["ci_guardrails"]["score"] == 60


def test_dispatch_readonly_worker_success(tmp_path: Path) -> None:
    """Successful dispatch returns parsed JSON."""
    agent_output = {
        "categories": {
            "ci_guardrails": {
                "score_adjustment": 5,
                "rationale": "Good CI",
                "gaps": [],
            }
        }
    }
    cli_output = {"result": json.dumps(agent_output)}

    with patch("action_harness.assess_agent.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(cli_output),
            stderr="",
        )
        result = dispatch_readonly_worker(
            prompt="test",
            system_prompt="test",
            worktree_path=tmp_path,
        )

    assert result is not None
    assert "categories" in result


def test_dispatch_readonly_worker_failure(tmp_path: Path) -> None:
    """Failed dispatch returns None."""
    with patch("action_harness.assess_agent.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="error"
        )
        result = dispatch_readonly_worker(
            prompt="test",
            system_prompt="test",
            worktree_path=tmp_path,
        )

    assert result is None


def test_dispatch_readonly_worker_timeout(tmp_path: Path) -> None:
    """Timeout returns None."""
    with patch("action_harness.assess_agent.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=300)
        result = dispatch_readonly_worker(
            prompt="test",
            system_prompt="test",
            worktree_path=tmp_path,
        )

    assert result is None


def test_dispatch_readonly_worker_claude_not_found(tmp_path: Path) -> None:
    """claude CLI not found returns None."""
    with patch("action_harness.assess_agent.subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError("claude")
        result = dispatch_readonly_worker(
            prompt="test",
            system_prompt="test",
            worktree_path=tmp_path,
        )

    assert result is None


def test_run_agent_assessment_fallback(tmp_path: Path) -> None:
    """run_agent_assessment falls back on dispatch failure."""
    categories = _make_categories()
    original_scores = {k: v.score for k, v in categories.items()}

    with patch("action_harness.assess_agent.dispatch_readonly_worker") as mock:
        mock.return_value = None  # simulate failure
        result = run_agent_assessment(categories, tmp_path)

    # Scores unchanged
    for k, v in result.items():
        assert v.score == original_scores[k]


def test_run_agent_assessment_merges(tmp_path: Path) -> None:
    """run_agent_assessment merges successful agent results."""
    categories = _make_categories()
    agent_output = {
        "categories": {
            "ci_guardrails": {
                "score_adjustment": 10,
                "rationale": "Good CI",
                "gaps": [],
            }
        }
    }

    with patch("action_harness.assess_agent.dispatch_readonly_worker") as mock:
        mock.return_value = agent_output
        result = run_agent_assessment(categories, tmp_path)

    assert result["ci_guardrails"].score == 70
    assert result["ci_guardrails"].agent_assessment == "Good CI"


def test_dispatch_readonly_worker_no_result_key(tmp_path: Path) -> None:
    """CLI output without 'result' key returns None."""
    cli_output = {"session_id": "abc", "cost_usd": 0.01}

    with patch("action_harness.assess_agent.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(cli_output),
            stderr="",
        )
        result = dispatch_readonly_worker(
            prompt="test",
            system_prompt="test",
            worktree_path=tmp_path,
        )

    assert result is None
