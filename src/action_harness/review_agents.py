"""Review agent dispatch: bug-hunter, test-reviewer, quality-reviewer."""

import concurrent.futures
import json
import subprocess
import time
from pathlib import Path

import typer

from action_harness.models import AcknowledgedFinding, ReviewFinding, ReviewResult
from action_harness.parsing import extract_json_block

# Agent names dispatched in parallel
REVIEW_AGENT_NAMES = ["bug-hunter", "test-reviewer", "quality-reviewer"]

# Severity ranking for tolerance-based filtering
SEVERITY_RANK: dict[str, int] = {"low": 0, "medium": 1, "high": 2, "critical": 3}
TOLERANCE_THRESHOLD: dict[str, int] = {"low": 0, "med": 1, "high": 2}

# --- Agent prompts (hardcoded, point-in-time copies) ---

_AGENT_PROMPTS: dict[str, str] = {
    "bug-hunter": """\
You are a deep bug-finding specialist reviewing a pull request.

Your job is to hunt for:
- Memory issues and resource leaks
- Race conditions and concurrency bugs
- Logic errors and off-by-one errors
- Edge cases that will crash or produce wrong results
- Unhandled error paths
- Security vulnerabilities

Review the PR diff by running `gh pr diff {pr_number}`. Read full files for
context as needed. Focus on correctness — find bugs that will cause real
problems, not style issues.

Do NOT modify any files. You are a read-only reviewer.
""",
    "test-reviewer": """\
You are a testing specialist reviewing a pull request.

Your job is to:
- Analyze test coverage for the changed code
- Identify untested code paths and edge cases
- Evaluate test correctness (do tests actually test what they claim?)
- Check for missing error-case tests
- Verify test isolation (no shared state, no order dependencies)

Review the PR diff by running `gh pr diff {pr_number}`. Read full files and
test files for context as needed. Focus on test completeness and correctness.

Do NOT modify any files. You are a read-only reviewer.
""",
    "quality-reviewer": """\
You are a code quality specialist reviewing a pull request.

Before reviewing, read the repo's CLAUDE.md (if it exists) and check linter
configuration in pyproject.toml or equivalent. Ground every finding in a
specific rule from these files or an observable existing pattern in the
codebase. Do not raise findings based on personal preference — cite the rule
you are enforcing.

Your job is to check:
- Correctness patterns and defensive coding
- Convention adherence and consistency with the codebase
- Maintainability risks (complexity, coupling, unclear naming)
- Architectural consistency with existing patterns
- API design and interface quality

Review the PR diff by running `gh pr diff {pr_number}`. Read full files for
context as needed. Focus on patterns that will cause maintenance burden.

Do NOT modify any files. You are a read-only reviewer.
""",
}

_JSON_OUTPUT_SUFFIX = """

After your review, output a single JSON block with your findings:

```json
{
  "findings": [
    {
      "title": "Brief description of the issue",
      "file": "path/to/file.py",
      "line": 42,
      "severity": "critical|high|medium|low",
      "description": "Detailed explanation of the issue and why it matters"
    }
  ],
  "summary": "One-sentence summary of your review"
}
```

If you find no issues, output:
```json
{"findings": [], "summary": "No issues found."}
```

The `line` field can be null if the issue is not tied to a specific line.
Severity levels:
- critical: Will cause data loss, security breach, or crash in production
- high: Will cause incorrect behavior that users will notice
- medium: Code smell or maintainability issue that should be addressed
- low: Minor style or convention issue
"""


def build_review_prompt(agent_name: str, pr_number: int) -> str:
    """Build the system prompt for a review agent.

    Raises ValueError for unknown agent names.
    """
    base = _AGENT_PROMPTS.get(agent_name)
    if base is None:
        raise ValueError(
            f"Unknown review agent: {agent_name!r}. "
            f"Expected one of: {', '.join(REVIEW_AGENT_NAMES)}"
        )
    return base.format(pr_number=pr_number) + _JSON_OUTPUT_SUFFIX


def dispatch_single_review(
    agent_name: str,
    pr_number: int,
    worktree_path: Path,
    max_turns: int = 50,
    model: str | None = None,
    effort: str | None = None,
    max_budget_usd: float | None = None,
    permission_mode: str = "bypassPermissions",
    verbose: bool = False,
) -> ReviewResult:
    """Dispatch a single review agent via Claude Code CLI.

    Builds and runs a `claude -p` command, parses structured findings.
    """
    typer.echo(f"[review:{agent_name}] dispatching for PR #{pr_number}", err=True)

    system_prompt = build_review_prompt(agent_name, pr_number)
    user_prompt = f"Review PR #{pr_number}"

    cmd = [
        "claude",
        "-p",
        user_prompt,
        "--system-prompt",
        system_prompt,
        "--output-format",
        "json",
        "--max-turns",
        str(max_turns),
        "--permission-mode",
        permission_mode,
    ]
    if model is not None:
        cmd.extend(["--model", model])
    if effort is not None:
        cmd.extend(["--effort", effort])
    if max_budget_usd is not None:
        cmd.extend(["--max-budget-usd", str(max_budget_usd)])

    if verbose:
        typer.echo(f"  cwd: {worktree_path}", err=True)
        typer.echo(f"  cmd: {' '.join(cmd[:6])}...", err=True)

    start_time = time.monotonic()

    try:
        result = subprocess.run(
            cmd,
            cwd=worktree_path,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        duration = time.monotonic() - start_time
        typer.echo(f"[review:{agent_name}] timed out after 600s", err=True)
        return ReviewResult(
            success=False,
            agent_name=agent_name,
            error="Claude CLI timed out after 600s",
            duration_seconds=duration,
        )
    except (FileNotFoundError, OSError) as e:
        duration = time.monotonic() - start_time
        typer.echo(f"[review:{agent_name}] failed to launch: {e}", err=True)
        return ReviewResult(
            success=False,
            agent_name=agent_name,
            error=f"Failed to launch claude CLI: {e}",
            duration_seconds=duration,
        )

    duration = time.monotonic() - start_time

    if result.returncode != 0:
        typer.echo(f"[review:{agent_name}] failed (exit {result.returncode})", err=True)
        return ReviewResult(
            success=False,
            agent_name=agent_name,
            error=f"Claude CLI exited with code {result.returncode}: {result.stderr[:500]}",
            duration_seconds=duration,
        )

    review_result = parse_review_findings(result.stdout, agent_name, duration)
    typer.echo(
        f"[review:{agent_name}] completed: {len(review_result.findings)} finding(s) "
        f"in {duration:.1f}s",
        err=True,
    )
    return review_result


def parse_review_findings(raw_output: str, agent_name: str, duration: float) -> ReviewResult:
    """Parse a review agent's JSON output into a ReviewResult.

    Extracts the JSON block from the Claude CLI JSON envelope's ``result``
    field. On parse failure, returns an error result.
    """
    cost_usd: float | None = None

    try:
        output_data = json.loads(raw_output)
        result_text = output_data.get("result", "")
        cost_usd = output_data.get("cost_usd")
    except (json.JSONDecodeError, TypeError):
        return ReviewResult(
            success=False,
            agent_name=agent_name,
            error="Failed to parse review output: invalid JSON from CLI",
            duration_seconds=duration,
        )

    review_data = extract_json_block(result_text)
    if review_data is None:
        return ReviewResult(
            success=False,
            agent_name=agent_name,
            error="Failed to parse review output: no JSON block found in result",
            duration_seconds=duration,
            cost_usd=cost_usd,
        )

    raw_findings = review_data.get("findings", [])
    findings: list[ReviewFinding] = []
    for f in raw_findings:
        if isinstance(f, dict):
            try:
                findings.append(
                    ReviewFinding(
                        title=f.get("title", "Untitled"),
                        file=f.get("file", "unknown"),
                        line=f.get("line"),
                        severity=f.get("severity", "medium"),
                        description=f.get("description", ""),
                        agent=agent_name,
                    )
                )
            except Exception as e:
                typer.echo(
                    f"[review:{agent_name}] warning: skipped malformed finding: {e}",
                    err=True,
                )

    return ReviewResult(
        success=True,
        agent_name=agent_name,
        findings=findings,
        duration_seconds=duration,
        cost_usd=cost_usd,
    )


def dispatch_review_agents(
    pr_number: int,
    worktree_path: Path,
    max_turns: int = 50,
    model: str | None = None,
    effort: str | None = None,
    max_budget_usd: float | None = None,
    permission_mode: str = "bypassPermissions",
    verbose: bool = False,
) -> list[ReviewResult]:
    """Dispatch all three review agents in parallel.

    Returns a list of ReviewResult, one per agent. All agents run to
    completion regardless of individual failures.
    """
    typer.echo(
        f"[review] dispatching {len(REVIEW_AGENT_NAMES)} agents for PR #{pr_number}",
        err=True,
    )
    start_time = time.monotonic()

    results: list[ReviewResult] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(
                dispatch_single_review,
                agent_name=name,
                pr_number=pr_number,
                worktree_path=worktree_path,
                max_turns=max_turns,
                model=model,
                effort=effort,
                max_budget_usd=max_budget_usd,
                permission_mode=permission_mode,
                verbose=verbose,
            ): name
            for name in REVIEW_AGENT_NAMES
        }

        for future in concurrent.futures.as_completed(futures):
            agent_name = futures[future]
            try:
                result = future.result()
            except Exception as e:
                result = ReviewResult(
                    success=False,
                    agent_name=agent_name,
                    error=f"Unexpected error: {e}",
                )
            results.append(result)

    total_duration = time.monotonic() - start_time
    typer.echo(f"[review] all agents completed in {total_duration:.1f}s", err=True)

    return results


def _titles_overlap(title_a: str, title_b: str) -> bool:
    """Check whether two titles share a meaningful word overlap.

    Uses case-insensitive comparison. Two titles overlap when either full
    title is a substring of the other, OR they share a contiguous sequence
    of 2+ words. Single-word matches (e.g. "Bug") are ignored to avoid
    false positives from common short words.
    """
    a_lower = title_a.lower()
    b_lower = title_b.lower()

    # Fast path: full-title substring
    if a_lower in b_lower or b_lower in a_lower:
        return True

    # Token-overlap: check if any contiguous 2+ word sequence from one
    # title appears in the other. This catches reworded titles like
    # "null check missing in handler" vs "Missing null check".
    a_words = a_lower.split()
    b_words = b_lower.split()
    if len(a_words) < 2 or len(b_words) < 2:
        return False

    # Build set of 2-word sequences from the shorter title, check against longer
    shorter, longer = (a_words, b_lower) if len(a_words) <= len(b_words) else (b_words, a_lower)
    for i in range(len(shorter) - 1):
        bigram = f"{shorter[i]} {shorter[i + 1]}"
        if bigram in longer:
            return True

    return False


def compute_finding_priority(finding: ReviewFinding, all_findings: list[ReviewFinding]) -> int:
    """Compute priority score for a finding based on severity and cross-agent agreement.

    Priority = ``SEVERITY_RANK[severity] * 10 + cross_agent_count`` where
    *cross_agent_count* is the number of distinct agents that flagged a finding
    on the same file with overlapping title text (case-insensitive token overlap).
    """
    finding_title = finding.title
    if not finding_title:
        return SEVERITY_RANK[finding.severity] * 10 + 1

    agents_with_overlap: set[str] = {finding.agent}
    for other in all_findings:
        if other.file != finding.file:
            continue
        if other.agent == finding.agent:
            continue
        if not other.title:
            continue
        if _titles_overlap(finding_title, other.title):
            agents_with_overlap.add(other.agent)
    cross_agent_count = len(agents_with_overlap)
    return SEVERITY_RANK[finding.severity] * 10 + cross_agent_count


def select_top_findings(
    findings: list[ReviewFinding], max_findings: int
) -> tuple[list[ReviewFinding], list[ReviewFinding]]:
    """Select top findings by priority, returning (selected, deferred).

    When ``max_findings <= 0``, all findings are returned as selected with
    an empty deferred list (no cap).
    """
    if max_findings <= 0:
        return list(findings), []

    scored = sorted(
        findings,
        key=lambda f: compute_finding_priority(f, findings),
        reverse=True,
    )
    selected = scored[:max_findings]
    deferred = scored[max_findings:]
    return selected, deferred


def filter_actionable_findings(results: list[ReviewResult], tolerance: str) -> list[ReviewFinding]:
    """Return findings at or above the tolerance threshold.

    A finding is actionable when ``SEVERITY_RANK[finding.severity] >=
    TOLERANCE_THRESHOLD[tolerance]``.
    """
    threshold = TOLERANCE_THRESHOLD[tolerance]
    actionable: list[ReviewFinding] = []
    for result in results:
        for finding in result.findings:
            if SEVERITY_RANK[finding.severity] >= threshold:
                actionable.append(finding)
    return actionable


def triage_findings(results: list[ReviewResult], tolerance: str = "low") -> bool:
    """Determine if review findings require a fix retry.

    Returns True when actionable findings exist at or above the tolerance
    threshold. Returns False otherwise (including when all results failed).
    """
    return len(filter_actionable_findings(results, tolerance)) > 0


def match_findings(prior: list[ReviewFinding], current: list[ReviewFinding]) -> list[ReviewFinding]:
    """Match current findings against prior findings.

    Two findings match if they share the same ``file`` field AND either:
    (a) the same ``agent`` field, or
    (b) one finding's ``title`` is a case-insensitive substring of the other's.

    Returns the subset of *current* findings that match any prior finding.
    """
    matched: list[ReviewFinding] = []
    for cur in current:
        for pri in prior:
            if cur.file != pri.file:
                continue
            # Same agent on same file → match
            if cur.agent == pri.agent:
                matched.append(cur)
                break
            # Title substring match (case-insensitive)
            cur_title_lower = cur.title.lower()
            pri_title_lower = pri.title.lower()
            if cur_title_lower in pri_title_lower or pri_title_lower in cur_title_lower:
                matched.append(cur)
                break
    return matched


def format_review_feedback(
    results: list[ReviewResult],
    tolerance: str = "low",
    prior_acknowledged: list[AcknowledgedFinding] | None = None,
    max_findings: int = 0,
) -> str:
    """Format actionable review findings as structured markdown feedback.

    Only includes findings at or above the tolerance threshold.
    When ``max_findings > 0``, selects the top N findings by priority and
    defers the rest (logged to stderr but not included in feedback).
    Appends a "Prior Acknowledged Findings" section if any exist.
    Used as the feedback string when re-dispatching the code worker.
    """
    actionable = filter_actionable_findings(results, tolerance)

    if max_findings > 0 and actionable:
        actionable, deferred = select_top_findings(actionable, max_findings)
        if deferred:
            typer.echo(
                f"[review] deferred {len(deferred)} finding(s) below priority cap",
                err=True,
            )

    lines = ["## Review Agent Findings", ""]

    if not actionable:
        return "## Review Agent Findings\n\nNo findings."

    # Group by agent
    by_agent: dict[str, list[ReviewFinding]] = {}
    for finding in actionable:
        by_agent.setdefault(finding.agent, []).append(finding)

    for agent_name, findings in by_agent.items():
        lines.append(f"### {agent_name}")
        for finding in findings:
            location = finding.file
            if finding.line is not None:
                location += f":{finding.line}"
            lines.append(f"#### [{finding.severity.upper()}] {finding.title}")
            lines.append(f"- **File:** {location}")
            lines.append(f"- **Description:** {finding.description}")
            lines.append("")

    lines.append(
        "For each finding, you MUST either fix it in code or post a PR comment "
        "explaining why no change is needed. If a finding appears under Prior "
        "Acknowledged Findings, add a code comment at the relevant location — "
        "two reviewers flagging the same concern means future readers will too."
    )
    lines.append("")

    if prior_acknowledged:
        lines.append("## Prior Acknowledged Findings")
        lines.append("")
        for ack in prior_acknowledged:
            f = ack.finding
            location = f.file
            if f.line is not None:
                location += f":{f.line}"
            lines.append(
                f"- **[{f.severity.upper()}]** {f.title} (`{location}`) "
                f"— first flagged in round {ack.acknowledged_in_round}"
            )
        lines.append("")

    lines.append("Fix the issues above and re-run eval to verify.")
    return "\n".join(lines)
