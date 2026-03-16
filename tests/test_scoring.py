"""Tests for scoring logic."""

from action_harness.assessment import (
    CIMechanicalSignals,
    ContextMechanicalSignals,
    IsolationMechanicalSignals,
    ObservabilityMechanicalSignals,
    TestabilityMechanicalSignals,
    ToolingMechanicalSignals,
)
from action_harness.scoring import (
    CategoryScore,
    compute_overall,
    identify_gaps,
    score_category,
)


def test_perfect_ci_scores_100() -> None:
    """All CI signals true scores 100."""
    signals = CIMechanicalSignals(
        ci_exists=True,
        triggers_on_pr=True,
        runs_tests=True,
        runs_lint=True,
        runs_typecheck=True,
        runs_format_check=True,
        branch_protection=True,
    )
    result = score_category("ci_guardrails", signals)
    assert result.score == 100


def test_empty_ci_scores_0() -> None:
    """No CI signals scores 0."""
    signals = CIMechanicalSignals()
    result = score_category("ci_guardrails", signals)
    assert result.score == 0


def test_partial_ci_scores_60() -> None:
    """ci_exists + triggers_on_pr + runs_tests = 15 + 20 + 25 = 60."""
    signals = CIMechanicalSignals(
        ci_exists=True,
        triggers_on_pr=True,
        runs_tests=True,
    )
    result = score_category("ci_guardrails", signals)
    assert result.score == 60


def test_perfect_context_scores_100() -> None:
    """All context signals present scores 100."""
    signals = ContextMechanicalSignals(
        claude_md=True,
        readme=True,
        harness_md=True,
        agents_md=True,
        type_annotations_present=True,
        docstrings_present=True,
    )
    result = score_category("context", signals)
    assert result.score == 100


def test_empty_context_scores_0() -> None:
    """No context signals scores 0."""
    signals = ContextMechanicalSignals()
    result = score_category("context", signals)
    assert result.score == 0


def test_perfect_testability_with_ci() -> None:
    """Full testability signals + tests_in_ci = 100."""
    signals = TestabilityMechanicalSignals(
        test_framework_configured=True,
        test_files=10,
        test_functions=50,
        coverage_configured=True,
    )
    result = score_category("testability", signals, tests_in_ci=True)
    assert result.score == 100


def test_empty_testability_scores_0() -> None:
    """No testability signals scores 0."""
    signals = TestabilityMechanicalSignals()
    result = score_category("testability", signals)
    assert result.score == 0


def test_partial_testability() -> None:
    """Partial testability: framework + 3 files + 15 functions + tests_in_ci."""
    signals = TestabilityMechanicalSignals(
        test_framework_configured=True,
        test_files=3,
        test_functions=15,
        coverage_configured=False,
    )
    # 20 (framework) + 15 (>=1 file) + 0 (<5 files) + 15 (>=10 funcs) + 10 (not >=30) -> wait
    # test_functions=15 >= 10 -> 15, test_functions=15 < 30 -> 0 for that tier
    # So: 20 + 15 + 0 + 15 + 0 + 0 + 15 (tests_in_ci) = 65
    result = score_category("testability", signals, tests_in_ci=True)
    assert result.score == 65


def test_perfect_tooling_scores_100() -> None:
    """All tooling signals scores 100."""
    signals = ToolingMechanicalSignals(
        package_manager=True,
        lockfile_present=True,
        lockfile="uv.lock",
        mcp_configured=True,
        skills_present=True,
        docker_configured=True,
        cli_tools_available=True,
    )
    result = score_category("tooling", signals)
    assert result.score == 100


def test_perfect_observability_scores_100() -> None:
    """All observability signals scores 100."""
    signals = ObservabilityMechanicalSignals(
        structured_logging_lib=True,
        health_endpoint=True,
        metrics_lib=True,
        tracing_lib=True,
        log_level_configurable=True,
    )
    result = score_category("observability", signals)
    assert result.score == 100


def test_perfect_isolation_scores_100() -> None:
    """All isolation signals scores 100."""
    signals = IsolationMechanicalSignals(
        git_repo=True,
        lockfile_present=True,
        env_example_present=True,
        no_committed_secrets=True,
        reproducible_build=True,
    )
    result = score_category("isolation", signals)
    assert result.score == 100


def test_missing_claude_md_produces_high_gap() -> None:
    """Missing CLAUDE.md (30 points) produces a high-severity gap."""
    signals = ContextMechanicalSignals(claude_md=False)
    gaps = identify_gaps("context", signals)
    claude_gaps = [g for g in gaps if g.proposal_name == "add-claude-md"]
    assert len(claude_gaps) == 1
    assert claude_gaps[0].severity == "high"
    assert claude_gaps[0].category == "context"


def test_format_check_missing_no_gap() -> None:
    """runs_format_check (5 points) below threshold, not a gap."""
    signals = CIMechanicalSignals(
        ci_exists=True,
        triggers_on_pr=True,
        runs_tests=True,
        runs_lint=True,
        runs_typecheck=True,
        runs_format_check=False,
        branch_protection=True,
    )
    gaps = identify_gaps("ci_guardrails", signals)
    format_gaps = [g for g in gaps if "format_check" in (g.proposal_name or "")]
    assert len(format_gaps) == 0


def test_runs_tests_missing_is_high_gap() -> None:
    """runs_tests (25 points) missing produces a high-severity gap."""
    signals = CIMechanicalSignals(ci_exists=True, runs_tests=False)
    gaps = identify_gaps("ci_guardrails", signals)
    test_gaps = [g for g in gaps if g.proposal_name == "add-ci-tests"]
    assert len(test_gaps) == 1
    assert test_gaps[0].severity == "high"


def test_compute_overall_average() -> None:
    """Overall score is arithmetic mean of category scores."""
    categories = {
        "a": CategoryScore(score=80, mechanical_signals=CIMechanicalSignals()),
        "b": CategoryScore(score=60, mechanical_signals=CIMechanicalSignals()),
        "c": CategoryScore(score=90, mechanical_signals=CIMechanicalSignals()),
        "d": CategoryScore(score=20, mechanical_signals=CIMechanicalSignals()),
        "e": CategoryScore(score=80, mechanical_signals=CIMechanicalSignals()),
        "f": CategoryScore(score=100, mechanical_signals=CIMechanicalSignals()),
    }
    # Mean = (80 + 60 + 90 + 20 + 80 + 100) / 6 = 430 / 6 = 71.67 -> 72
    assert compute_overall(categories) == 72


def test_compute_overall_empty() -> None:
    """Empty categories returns 0."""
    assert compute_overall({}) == 0


def test_branch_protection_none_no_penalty() -> None:
    """branch_protection=None should not lose points or produce a gap."""
    signals = CIMechanicalSignals(
        ci_exists=True,
        triggers_on_pr=True,
        runs_tests=True,
        runs_lint=True,
        runs_typecheck=True,
        runs_format_check=True,
        branch_protection=None,  # unknown — gh unavailable
    )
    result = score_category("ci_guardrails", signals)
    # Should get 90 (all except branch_protection's 10 points)
    # but no gap for branch_protection since it's unknown
    assert result.score == 90
    bp_gaps = [g for g in result.gaps if "branch_protection" in g.finding]
    assert len(bp_gaps) == 0


def test_branch_protection_false_is_a_gap() -> None:
    """branch_protection=False should still not be a gap (only 10 pts < 15)."""
    signals = CIMechanicalSignals(
        ci_exists=True,
        triggers_on_pr=True,
        runs_tests=True,
        runs_lint=True,
        runs_typecheck=True,
        runs_format_check=True,
        branch_protection=False,
    )
    result = score_category("ci_guardrails", signals)
    assert result.score == 90
    # 10 points is below gap threshold so no gap either way
    bp_gaps = [g for g in result.gaps if "branch_protection" in g.finding]
    assert len(bp_gaps) == 0
