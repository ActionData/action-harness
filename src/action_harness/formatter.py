"""Terminal output formatting for assessment reports."""

import typer

from action_harness.assessment import AssessmentReport, Gap

# Block characters for score bars
_FULL_BLOCK = "█"
_EMPTY_BLOCK = "░"


def _score_bar(score: int) -> str:
    """Build a 10-block bar where each block = 10 points."""
    filled = score // 10
    empty = 10 - filled
    return _FULL_BLOCK * filled + _EMPTY_BLOCK * empty


def _severity_label(severity: str) -> str:
    """Format a severity label for terminal output."""
    labels = {
        "high": "[HIGH]",
        "medium": "[MED]",
        "low": "[LOW]",
    }
    return labels.get(severity, f"[{severity.upper()}]")


def format_report(report: AssessmentReport, deep: bool = False, propose: bool = False) -> str:
    """Format an AssessmentReport for terminal display.

    Returns a string suitable for printing to stderr.
    """
    lines: list[str] = []
    lines.append("")
    lines.append(f"Codebase Assessment — {report.repo_path}")
    lines.append(f"Mode: {report.mode}")
    lines.append("")

    # Category scores
    category_order = [
        "ci_guardrails",
        "testability",
        "context",
        "tooling",
        "observability",
        "isolation",
    ]

    for cat_name in category_order:
        cat = report.categories.get(cat_name)
        if cat is None:
            continue

        bar = _score_bar(cat.score)
        display_name = cat_name.replace("_", " ").title()
        lines.append(f"  {display_name:<20} {cat.score:>3}  {bar}")

        # In deep mode, show agent rationale
        if deep and cat.agent_assessment:
            lines.append(f"    Agent: {cat.agent_assessment}")

        # Show gaps
        for gap in cat.gaps:
            label = _severity_label(gap.severity)
            lines.append(f"    {label} {gap.finding}")

        lines.append("")

    # Overall score
    lines.append(f"  {'Overall':<20} {report.overall_score:>3}  {_score_bar(report.overall_score)}")
    lines.append("")

    # Proposals section (--propose mode)
    if propose and report.proposals:
        lines.append("Generated Proposals:")
        for gap in report.proposals:
            if gap.proposal_name:
                lines.append(f"  - {gap.proposal_name} (openspec/changes/{gap.proposal_name}/)")
        lines.append("")

    return "\n".join(lines)


def print_report(report: AssessmentReport, deep: bool = False, propose: bool = False) -> None:
    """Print formatted assessment report to stderr."""
    output = format_report(report, deep=deep, propose=propose)
    typer.echo(output, err=True)


def collect_proposals(report: AssessmentReport) -> list[Gap]:
    """Collect all gaps with proposal names from the report."""
    proposals: list[Gap] = []
    for cat in report.categories.values():
        for gap in cat.gaps:
            if gap.proposal_name:
                proposals.append(gap)
    return proposals
