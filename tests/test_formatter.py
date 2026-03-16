"""Tests for terminal output formatting."""

from action_harness.assessment import (
    AssessmentReport,
    CategoryScore,
    CIMechanicalSignals,
    ContextMechanicalSignals,
    Gap,
    IsolationMechanicalSignals,
    ObservabilityMechanicalSignals,
    TestabilityMechanicalSignals,
    ToolingMechanicalSignals,
)
from action_harness.formatter import (
    _score_bar,
    _severity_label,
    collect_proposals,
    format_report,
)


def test_score_bar_zero() -> None:
    """Score 0 produces all empty blocks."""
    bar = _score_bar(0)
    assert bar == "░" * 10


def test_score_bar_100() -> None:
    """Score 100 produces all filled blocks."""
    bar = _score_bar(100)
    assert bar == "█" * 10


def test_score_bar_50() -> None:
    """Score 50 produces 5 filled + 5 empty."""
    bar = _score_bar(50)
    assert bar == "█" * 5 + "░" * 5


def test_score_bar_5() -> None:
    """Score 5 rounds down to 0 filled blocks."""
    bar = _score_bar(5)
    assert bar == "░" * 10


def test_score_bar_95() -> None:
    """Score 95 produces 9 filled + 1 empty."""
    bar = _score_bar(95)
    assert bar == "█" * 9 + "░"


def test_severity_label_high() -> None:
    assert _severity_label("high") == "[HIGH]"


def test_severity_label_medium() -> None:
    assert _severity_label("medium") == "[MED]"


def test_severity_label_low() -> None:
    assert _severity_label("low") == "[LOW]"


def test_severity_label_unknown() -> None:
    assert _severity_label("critical") == "[CRITICAL]"


def _make_report(deep: bool = False, proposals: list[Gap] | None = None) -> AssessmentReport:
    gap = Gap(
        severity="high",
        finding="No tests",
        category="ci_guardrails",
        proposal_name="add-ci-tests",
    )
    return AssessmentReport(
        overall_score=50,
        categories={
            "ci_guardrails": CategoryScore(
                score=60,
                mechanical_signals=CIMechanicalSignals(),
                agent_assessment="CI is decent" if deep else None,
                gaps=[gap],
            ),
            "testability": CategoryScore(
                score=40,
                mechanical_signals=TestabilityMechanicalSignals(),
            ),
            "context": CategoryScore(
                score=50,
                mechanical_signals=ContextMechanicalSignals(),
            ),
            "tooling": CategoryScore(
                score=60,
                mechanical_signals=ToolingMechanicalSignals(),
            ),
            "observability": CategoryScore(
                score=30,
                mechanical_signals=ObservabilityMechanicalSignals(),
            ),
            "isolation": CategoryScore(
                score=80,
                mechanical_signals=IsolationMechanicalSignals(),
            ),
        },
        proposals=proposals or [],
        repo_path="/tmp/test",
        timestamp="2025-01-01T00:00:00Z",
        mode="deep" if deep else "base",
    )


def test_format_report_contains_categories() -> None:
    """Report output contains all six category names."""
    report = _make_report()
    output = format_report(report)
    assert "Ci Guardrails" in output
    assert "Testability" in output
    assert "Context" in output
    assert "Tooling" in output
    assert "Observability" in output
    assert "Isolation" in output
    assert "Overall" in output


def test_format_report_contains_scores() -> None:
    """Report output contains numeric scores."""
    report = _make_report()
    output = format_report(report)
    assert " 60 " in output  # CI score
    assert " 50 " in output  # Overall


def test_format_report_contains_gaps() -> None:
    """Report output contains gap findings."""
    report = _make_report()
    output = format_report(report)
    assert "[HIGH]" in output
    assert "No tests" in output


def test_format_report_deep_shows_rationale() -> None:
    """Deep mode shows agent rationale."""
    report = _make_report(deep=True)
    output = format_report(report, deep=True)
    assert "Agent: CI is decent" in output


def test_format_report_base_no_rationale() -> None:
    """Base mode does not show agent rationale."""
    report = _make_report(deep=False)
    output = format_report(report, deep=False)
    assert "Agent:" not in output


def test_format_report_propose_shows_proposals() -> None:
    """Propose mode shows generated proposals."""
    gap = Gap(
        severity="high",
        finding="No tests",
        category="ci_guardrails",
        proposal_name="add-ci-tests",
    )
    report = _make_report(proposals=[gap])
    output = format_report(report, propose=True)
    assert "Generated Proposals:" in output
    assert "add-ci-tests" in output


def test_collect_proposals_filters_named_gaps() -> None:
    """collect_proposals only returns gaps with proposal_name."""
    categories = {
        "ci": CategoryScore(
            score=50,
            mechanical_signals=CIMechanicalSignals(),
            gaps=[
                Gap(
                    severity="high",
                    finding="Gap with name",
                    category="ci",
                    proposal_name="fix-it",
                ),
                Gap(
                    severity="low",
                    finding="Gap without name",
                    category="ci",
                    proposal_name=None,
                ),
            ],
        ),
    }
    proposals = collect_proposals(categories)
    assert len(proposals) == 1
    assert proposals[0].proposal_name == "fix-it"
