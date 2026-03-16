"""Tests for assessment models."""

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


def _make_report() -> AssessmentReport:
    """Build a sample AssessmentReport for testing."""
    ci_gap = Gap(
        severity="high",
        finding="No CI tests configured",
        category="ci_guardrails",
        proposal_name="add-ci-tests",
    )
    return AssessmentReport(
        overall_score=55,
        categories={
            "ci_guardrails": CategoryScore(
                score=60,
                mechanical_signals=CIMechanicalSignals(
                    ci_exists=True,
                    triggers_on_pr=True,
                    runs_tests=True,
                ),
                gaps=[ci_gap],
            ),
            "testability": CategoryScore(
                score=40,
                mechanical_signals=TestabilityMechanicalSignals(
                    test_framework_configured=True,
                    test_files=3,
                    test_functions=12,
                ),
            ),
            "context": CategoryScore(
                score=50,
                mechanical_signals=ContextMechanicalSignals(
                    claude_md=True,
                    readme=True,
                ),
            ),
            "tooling": CategoryScore(
                score=60,
                mechanical_signals=ToolingMechanicalSignals(
                    package_manager=True,
                    lockfile_present=True,
                    lockfile="uv.lock",
                ),
            ),
            "observability": CategoryScore(
                score=30,
                mechanical_signals=ObservabilityMechanicalSignals(
                    structured_logging_lib=True,
                ),
            ),
            "isolation": CategoryScore(
                score=90,
                mechanical_signals=IsolationMechanicalSignals(
                    git_repo=True,
                    lockfile_present=True,
                    env_example_present=True,
                    no_committed_secrets=True,
                    reproducible_build=True,
                ),
            ),
        },
        proposals=[ci_gap],
        repo_path="/tmp/test-repo",
        timestamp="2025-01-01T00:00:00Z",
        mode="base",
    )


def test_assessment_report_roundtrip() -> None:
    """AssessmentReport survives JSON roundtrip with all fields preserved."""
    report = _make_report()
    json_str = report.model_dump_json()
    restored = AssessmentReport.model_validate_json(json_str)

    assert restored.overall_score == report.overall_score
    assert restored.repo_path == report.repo_path
    assert restored.timestamp == report.timestamp
    assert restored.mode == report.mode

    # Nested field: gap proposal_name
    ci_gaps = restored.categories["ci_guardrails"].gaps
    assert len(ci_gaps) == 1
    assert ci_gaps[0].proposal_name == "add-ci-tests"
    assert ci_gaps[0].severity == "high"

    # CategoryScore.score preserved
    assert restored.categories["ci_guardrails"].score == 60
    assert restored.categories["testability"].score == 40

    # Proposals list preserved
    assert len(restored.proposals) == 1
    assert restored.proposals[0].proposal_name == "add-ci-tests"


def test_overall_score_is_mean() -> None:
    """Overall score should be the arithmetic mean of category scores."""
    report = _make_report()
    scores = [cat.score for cat in report.categories.values()]
    expected_mean = round(sum(scores) / len(scores))
    assert report.overall_score == expected_mean


def test_gap_without_proposal_name() -> None:
    """Gap with proposal_name=None roundtrips correctly."""
    gap = Gap(severity="low", finding="Minor issue", category="context", proposal_name=None)
    json_str = gap.model_dump_json()
    restored = Gap.model_validate_json(json_str)
    assert restored.proposal_name is None
    assert restored.severity == "low"


def test_mechanical_signals_defaults() -> None:
    """Mechanical signal models have sensible defaults."""
    ci = CIMechanicalSignals()
    assert ci.ci_exists is False
    assert ci.branch_protection is None

    test = TestabilityMechanicalSignals()
    assert test.test_files == 0
    assert test.test_functions == 0

    iso = IsolationMechanicalSignals()
    assert iso.no_committed_secrets is True
