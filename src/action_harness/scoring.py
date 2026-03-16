"""Scoring logic for codebase assessment."""

from typing import Literal

from action_harness.assessment import (
    CategoryScore,
    CIMechanicalSignals,
    ContextMechanicalSignals,
    Gap,
    IsolationMechanicalSignals,
    MechanicalSignalsUnion,
    ObservabilityMechanicalSignals,
    TestabilityMechanicalSignals,
    ToolingMechanicalSignals,
)

# Scoring weights per category.
# Each entry: (field_name, points, threshold_for_int_fields, proposal_name)
# For bool fields: True = earned, threshold is ignored.
# For int fields: value >= threshold = earned.

_CI_WEIGHTS: list[tuple[str, int, int | None, str]] = [
    ("ci_exists", 15, None, "add-ci"),
    ("triggers_on_pr", 20, None, "add-pr-trigger"),
    ("runs_tests", 25, None, "add-ci-tests"),
    ("runs_lint", 15, None, "add-ci-lint"),
    ("runs_typecheck", 10, None, "add-ci-typecheck"),
    ("runs_format_check", 5, None, "add-ci-format-check"),
    ("branch_protection", 10, None, "add-branch-protection"),
]

_TESTABILITY_WEIGHTS: list[tuple[str, int, int | None, str]] = [
    ("test_framework_configured", 20, None, "add-test-framework"),
    ("test_files", 15, 1, "add-test-files"),
    ("test_files", 10, 5, "add-more-test-files"),
    ("test_functions", 15, 10, "add-test-functions"),
    ("test_functions", 10, 30, "add-more-test-functions"),
    ("coverage_configured", 15, None, "add-coverage-config"),
]

_CONTEXT_WEIGHTS: list[tuple[str, int, int | None, str]] = [
    ("claude_md", 30, None, "add-claude-md"),
    ("readme", 20, None, "add-readme"),
    ("harness_md", 15, None, "add-harness-md"),
    ("agents_md", 10, None, "add-agents-md"),
    ("type_annotations_present", 15, None, "add-type-annotations"),
    ("docstrings_present", 10, None, "add-docstrings"),
]

_TOOLING_WEIGHTS: list[tuple[str, int, int | None, str]] = [
    ("package_manager", 20, None, "add-package-manager"),
    ("lockfile_present", 20, None, "add-lockfile"),
    ("mcp_configured", 15, None, "add-mcp-config"),
    ("skills_present", 15, None, "add-skills"),
    ("docker_configured", 15, None, "add-docker"),
    ("cli_tools_available", 15, None, "add-cli-tools"),
]

_OBSERVABILITY_WEIGHTS: list[tuple[str, int, int | None, str]] = [
    ("structured_logging_lib", 30, None, "add-structured-logging"),
    ("health_endpoint", 20, None, "add-health-endpoint"),
    ("metrics_lib", 20, None, "add-metrics"),
    ("tracing_lib", 15, None, "add-tracing"),
    ("log_level_configurable", 15, None, "add-log-level-config"),
]

_ISOLATION_WEIGHTS: list[tuple[str, int, int | None, str]] = [
    ("git_repo", 15, None, "add-git-repo"),
    ("lockfile_present", 20, None, "add-lockfile"),
    ("env_example_present", 20, None, "add-env-example"),
    ("no_committed_secrets", 25, None, "remove-committed-secrets"),
    ("reproducible_build", 20, None, "add-reproducible-build"),
]

_CATEGORY_WEIGHTS: dict[str, list[tuple[str, int, int | None, str]]] = {
    "ci_guardrails": _CI_WEIGHTS,
    "testability": _TESTABILITY_WEIGHTS,
    "context": _CONTEXT_WEIGHTS,
    "tooling": _TOOLING_WEIGHTS,
    "observability": _OBSERVABILITY_WEIGHTS,
    "isolation": _ISOLATION_WEIGHTS,
}


def _signal_is_unknown(signals: MechanicalSignalsUnion, field: str) -> bool:
    """Check if a signal value is None (unknown/couldn't check)."""
    return getattr(signals, field, None) is None


def _signal_earned(signals: MechanicalSignalsUnion, field: str, threshold: int | None) -> bool:
    """Check if a signal is earned (True for bools, >= threshold for ints).

    Returns False for None values (unknown), but callers should use
    _signal_is_unknown() to distinguish "not configured" from "couldn't check".
    """
    value = getattr(signals, field, None)
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and threshold is not None:
        return value >= threshold
    return False


def score_category(
    category: str,
    signals: MechanicalSignalsUnion,
    tests_in_ci: bool = False,
) -> CategoryScore:
    """Compute a 0-100 score for a category from mechanical signals.

    For testability, tests_in_ci adds 15 bonus points (from CI guardrails).
    """
    weights = _CATEGORY_WEIGHTS.get(category, [])
    total = 0

    for field, points, threshold, _proposal in weights:
        if _signal_earned(signals, field, threshold):
            total += points

    # Special: testability gets bonus for tests running in CI
    if category == "testability" and tests_in_ci:
        total += 15

    total = min(total, 100)

    gaps = identify_gaps(category, signals)

    return CategoryScore(
        score=total,
        mechanical_signals=signals,
        gaps=gaps,
    )


def identify_gaps(category: str, signals: MechanicalSignalsUnion) -> list[Gap]:
    """Identify gaps for sub-signals worth >= 15 points that are not earned.

    Severity: >= 25 = high, >= 15 = medium, < 15 = low (but those are
    filtered out since they don't become gaps).

    Signals with value None (unknown/couldn't check) are skipped — they
    represent inability to assess, not a confirmed gap.

    For graduated thresholds (e.g. test_files at 1 and 5), only the
    lowest unmet threshold produces a gap to avoid duplicates.
    """
    weights = _CATEGORY_WEIGHTS.get(category, [])
    gaps: list[Gap] = []
    # Track fields that already have a gap to avoid duplicates from
    # graduated thresholds (e.g. test_files at threshold 1 and 5).
    fields_with_gaps: set[str] = set()

    for field, points, threshold, proposal_name in weights:
        if points < 15:
            continue  # Below gap threshold

        if field in fields_with_gaps:
            continue  # Already reported a gap for this field

        if _signal_is_unknown(signals, field):
            continue  # Unknown signal — can't assess, not a gap

        if _signal_earned(signals, field, threshold):
            continue  # Signal is present, no gap

        severity: Literal["high", "medium"] = "high" if points >= 25 else "medium"

        # Build finding description
        if threshold is not None:
            finding = f"{field} is below threshold ({threshold})"
        else:
            finding = f"{field} is not configured"

        gaps.append(
            Gap(
                severity=severity,
                finding=finding,
                category=category,
                proposal_name=proposal_name,
            )
        )
        fields_with_gaps.add(field)

    return gaps


def compute_overall(categories: dict[str, CategoryScore]) -> int:
    """Compute overall score as arithmetic mean of category scores."""
    if not categories:
        return 0
    scores = [cat.score for cat in categories.values()]
    return round(sum(scores) / len(scores))


def score_all_categories(
    ci_signals: CIMechanicalSignals,
    testability_signals: TestabilityMechanicalSignals,
    context_signals: ContextMechanicalSignals,
    tooling_signals: ToolingMechanicalSignals,
    observability_signals: ObservabilityMechanicalSignals,
    isolation_signals: IsolationMechanicalSignals,
) -> dict[str, CategoryScore]:
    """Score all six categories and return the categories dict."""
    categories: dict[str, CategoryScore] = {
        "ci_guardrails": score_category("ci_guardrails", ci_signals),
        "testability": score_category(
            "testability", testability_signals, tests_in_ci=ci_signals.runs_tests
        ),
        "context": score_category("context", context_signals),
        "tooling": score_category("tooling", tooling_signals),
        "observability": score_category("observability", observability_signals),
        "isolation": score_category("isolation", isolation_signals),
    }
    return categories
