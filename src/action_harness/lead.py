"""Repo lead: context gathering, dispatch, and plan parsing for the lead agent."""

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import typer
from pydantic import BaseModel

from action_harness.agents import load_agent_prompt
from action_harness.parsing import extract_json_block

# ---------------------------------------------------------------------------
# Pydantic models for the lead plan
# ---------------------------------------------------------------------------


class ProposalItem(BaseModel):
    """A proposed OpenSpec change."""

    name: str
    description: str
    priority: str = "medium"


class IssueItem(BaseModel):
    """A GitHub issue to create."""

    title: str
    body: str
    labels: list[str] = []


class DispatchItem(BaseModel):
    """A harness dispatch recommendation."""

    change: str


class LeadPlan(BaseModel):
    """Structured plan output from the lead agent."""

    summary: str = ""
    proposals: list[ProposalItem] = []
    issues: list[IssueItem] = []
    dispatches: list[DispatchItem] = []


# ---------------------------------------------------------------------------
# Structured context model
# ---------------------------------------------------------------------------


@dataclass
class LeadContext:
    """Structured context gathered for the lead agent.

    Holds both the assembled flat text (for system prompt injection) and
    structured fields used by the greeting builder.
    """

    full_text: str = ""
    repo_name: str = ""
    active_changes: list[str] = field(default_factory=list)
    ready_changes: list[str] = field(default_factory=list)
    recent_run_stats: tuple[int, int] | None = None  # (passed, total)
    has_roadmap: bool = False
    has_claude_md: bool = False


# ---------------------------------------------------------------------------
# Context gathering
# ---------------------------------------------------------------------------


def _read_file_section(path: Path, header: str, max_chars: int) -> str | None:
    """Read a file and format as a markdown section, truncating to max_chars.

    Returns None if the file doesn't exist or can't be read.
    """
    if not path.is_file():
        return None
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        typer.echo(f"[lead] warning: could not read {path}: {exc}", err=True)
        return None
    if not content.strip():
        return None
    truncated = content[:max_chars]
    if len(content) > max_chars:
        truncated += "\n\n... (truncated)"
    return f"## {header}\n\n{truncated}"


def _gather_issues(repo_path: Path, max_section_chars: int) -> str | None:
    """Gather open GitHub issues via gh CLI. Returns None on failure."""
    typer.echo("[lead] gathering open issues via gh", err=True)
    try:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "list",
                "--json",
                "title,body,labels",
                "--limit",
                "20",
                "--state",
                "open",
            ],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (FileNotFoundError, OSError) as exc:
        typer.echo(f"[lead] warning: gh not available: {exc}", err=True)
        return None
    except subprocess.TimeoutExpired:
        typer.echo("[lead] warning: gh issue list timed out", err=True)
        return None

    if result.returncode != 0:
        typer.echo(
            f"[lead] warning: gh issue list failed (exit {result.returncode}): "
            f"{result.stderr[:200]}",
            err=True,
        )
        return None

    try:
        issues = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        typer.echo("[lead] warning: could not parse gh issue list output", err=True)
        return None

    if not issues:
        return None

    lines = ["## Open Issues", ""]
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        title = issue.get("title", "Untitled")
        body = issue.get("body", "") or ""
        labels_raw = issue.get("labels", [])
        label_names = []
        for lbl in labels_raw:
            if isinstance(lbl, dict):
                label_names.append(lbl.get("name", ""))
            elif isinstance(lbl, str):
                label_names.append(lbl)
        # Truncate each issue body to 500 chars
        if len(body) > 500:
            body = body[:500] + "..."
        label_str = f" [{', '.join(label_names)}]" if label_names else ""
        lines.append(f"### {title}{label_str}")
        if body:
            lines.append(body)
        lines.append("")

    section = "\n".join(lines)
    if len(section) > max_section_chars:
        section = section[:max_section_chars] + "\n\n... (truncated)"
    return section


def _gather_assessment_scores(repo_path: Path, max_section_chars: int) -> str | None:
    """Gather assessment scores via a quick base scan.

    Runs the mechanical scanners (no LLM) to produce category scores.
    Returns None on failure so assessment issues never block the lead.
    """
    typer.echo("[lead] gathering assessment scores (base scan)", err=True)
    try:
        from action_harness.assessment import CategoryScore
        from action_harness.branch_protection import check_branch_protection
        from action_harness.ci_parser import parse_github_actions
        from action_harness.profiler import profile_repo
        from action_harness.scanner import (
            analyze_test_structure,
            detect_context_signals,
            detect_isolation_signals,
            detect_observability_signals,
            detect_tooling_signals,
        )
        from action_harness.scoring import compute_overall, score_all_categories

        profile = profile_repo(repo_path)
        bp = check_branch_protection(repo_path)
        ci_signals = parse_github_actions(repo_path, branch_protection=bp)
        testability_signals = analyze_test_structure(repo_path, profile.ecosystem)
        context_signals = detect_context_signals(repo_path)
        tooling_signals = detect_tooling_signals(repo_path)
        observability_signals = detect_observability_signals(repo_path)
        isolation_signals = detect_isolation_signals(repo_path)

        categories: dict[str, CategoryScore] = score_all_categories(
            ci_signals=ci_signals,
            testability_signals=testability_signals,
            context_signals=context_signals,
            tooling_signals=tooling_signals,
            observability_signals=observability_signals,
            isolation_signals=isolation_signals,
        )
        overall = compute_overall(categories)

        lines = ["## Assessment Scores", "", f"**Overall: {overall}/100**", ""]
        for name, cat in categories.items():
            lines.append(f"- **{name}**: {cat.score}/100")
        lines.append("")

        section = "\n".join(lines)
        if len(section) > max_section_chars:
            section = section[:max_section_chars] + "\n\n... (truncated)"
        return section
    except Exception as exc:  # noqa: BLE001 — broad catch intentional:
        # Assessment calls 6+ scanner modules, branch protection (subprocess),
        # and CI parsing. Any failure in this optional context section must not
        # block the lead agent. Narrowing to specific exceptions would require
        # auditing every scanner's failure modes and updating on each change.
        typer.echo(f"[lead] warning: assessment scan failed: {exc}", err=True)
        return None


def _gather_recent_runs(
    repo_path: Path, max_section_chars: int
) -> tuple[str | None, tuple[int, int] | None]:
    """Gather recent run summary and structured stats from manifests.

    Returns ``(section_text, (passed, total))`` in a single pass.
    Either value may be ``None`` if no manifests exist or on error.
    """
    typer.echo("[lead] gathering recent run data", err=True)
    try:
        # Lazy import to avoid circular dependencies
        from action_harness.reporting import compute_run_stats, load_manifests

        manifests = load_manifests(repo_path)
    except Exception as exc:  # noqa: BLE001 — optional context, must not block lead
        typer.echo(f"[lead] warning: could not load manifests: {exc}", err=True)
        return (None, None)

    if not manifests:
        return (None, None)

    # Take last 5
    recent = manifests[-5:]
    stats = compute_run_stats(recent)
    run_stats: tuple[int, int] = (stats.passed, stats.total)

    lines = ["## Recent Harness Runs", ""]
    for m in recent:
        status = "success" if m.success else "failure"
        duration = f"{m.total_duration_seconds:.0f}s" if m.total_duration_seconds else "?"
        lines.append(f"- **{m.change_name}**: {status} ({duration})")
    lines.append("")

    section = "\n".join(lines)
    if len(section) > max_section_chars:
        section = section[:max_section_chars] + "\n\n... (truncated)"
    return (section, run_stats)


def _gather_catalog_frequency(harness_home: Path | None, max_section_chars: int) -> str | None:
    """Gather top catalog frequency entries from harness home knowledge store."""
    if harness_home is None:
        return None

    typer.echo("[lead] gathering catalog frequency data", err=True)

    from action_harness.catalog.frequency import FREQUENCY_FILENAME

    frequency_path = harness_home / "knowledge" / FREQUENCY_FILENAME
    if not frequency_path.is_file():
        return None

    try:
        raw = frequency_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        typer.echo(f"[lead] warning: could not read frequency file: {exc}", err=True)
        return None

    if not isinstance(data, dict) or not data:
        return None

    # Sort by count descending, take top 5
    def _get_count(entry: dict[str, str | int]) -> int:
        count = entry.get("count", 0)
        return count if isinstance(count, int) else 0

    entries = sorted(
        [(k, v) for k, v in data.items() if isinstance(v, dict)],
        key=lambda t: _get_count(t[1]),
        reverse=True,
    )[:5]

    if not entries:
        return None

    lines = ["## Top Catalog Findings", ""]
    for entry_id, entry_data in entries:
        count = entry_data.get("count", 0)
        lines.append(f"- **{entry_id}**: {count} occurrences")
    lines.append("")

    section = "\n".join(lines)
    if len(section) > max_section_chars:
        section = section[:max_section_chars] + "\n\n... (truncated)"
    return section


def _format_ready_changes_section(
    ready_names: list[str],
    blocked_list: list[dict[str, str | list[str]]],
    max_section_chars: int,
) -> str | None:
    """Format a "Ready Changes" section from pre-computed readiness data.

    Returns a markdown section listing changes ready for implementation,
    or a note if no changes are ready. Returns None if there are no active
    changes at all.
    """
    if not ready_names and not blocked_list:
        # No active changes at all — include a note
        return "## Ready Changes\n\nNo changes currently ready for implementation."

    lines = ["## Ready Changes", ""]
    if ready_names:
        for name in ready_names:
            lines.append(f"- {name}")
    else:
        lines.append("No changes currently ready for implementation.")
    lines.append("")

    section = "\n".join(lines)
    if len(section) > max_section_chars:
        section = section[:max_section_chars] + "\n\n... (truncated)"
    return section


def gather_lead_context(
    repo_path: Path,
    harness_home: Path | None = None,
    max_section_chars: int = 3000,
) -> LeadContext:
    """Gather repo context for the lead agent.

    Reads and assembles context sections, truncating each to max_section_chars:
    (a) ROADMAP.md, (b) CLAUDE.md, (c) HARNESS.md, (d) open issues,
    (e) assessment scores (quick base scan), (f) recent run summary,
    (g) catalog frequency top entries, (h) ready changes.

    Returns a :class:`LeadContext` with both the assembled flat text and
    structured fields for the greeting builder.
    """
    typer.echo(
        f"[lead] gathering context for {repo_path} (max_section_chars={max_section_chars})",
        err=True,
    )

    sections: list[str] = []
    lead_ctx = LeadContext(repo_name=repo_path.name)

    # (a) ROADMAP.md — check openspec directory first, then repo root
    roadmap_path = repo_path / "openspec" / "ROADMAP.md"
    if not roadmap_path.is_file():
        roadmap_path = repo_path / "ROADMAP.md"
    roadmap = _read_file_section(roadmap_path, "Roadmap", max_section_chars)
    if roadmap:
        sections.append(roadmap)
        lead_ctx.has_roadmap = True

    # (b) CLAUDE.md
    claude_md = _read_file_section(
        repo_path / "CLAUDE.md", "Project Context (CLAUDE.md)", max_section_chars
    )
    if claude_md:
        sections.append(claude_md)
        lead_ctx.has_claude_md = True

    # (c) HARNESS.md
    harness_md = _read_file_section(
        repo_path / "HARNESS.md", "Harness Configuration (HARNESS.md)", max_section_chars
    )
    if harness_md:
        sections.append(harness_md)

    # (d) Open issues
    issues = _gather_issues(repo_path, max_section_chars)
    if issues:
        sections.append(issues)

    # (e) Assessment scores
    assessment = _gather_assessment_scores(repo_path, max_section_chars)
    if assessment:
        sections.append(assessment)

    # (f) Recent run summary — single load_manifests call produces both the
    #     text section and the structured stats for the greeting builder.
    runs_section, run_stats = _gather_recent_runs(repo_path, max_section_chars)
    if runs_section:
        sections.append(runs_section)
    lead_ctx.recent_run_stats = run_stats

    # (g) Catalog frequency
    freq = _gather_catalog_frequency(harness_home, max_section_chars)
    if freq:
        sections.append(freq)

    # (h) Ready changes (from prerequisites) — single compute_readiness call
    #     feeds both the structured LeadContext fields and the text section.
    typer.echo("[lead] gathering ready changes from prerequisites", err=True)
    ready_names, blocked_list = _compute_readiness_safe(repo_path)
    lead_ctx.ready_changes = list(ready_names)
    lead_ctx.active_changes = _build_active_names(ready_names, blocked_list)

    ready_section = _format_ready_changes_section(ready_names, blocked_list, max_section_chars)
    if ready_section:
        sections.append(ready_section)

    if not sections:
        typer.echo("[lead] no context found — repo may need bootstrapping", err=True)
        lead_ctx.full_text = (
            "# Repo Context\n\n"
            "No context files found. "
            "This repo may need initial setup (ROADMAP.md, CLAUDE.md)."
        )
        return lead_ctx

    lead_ctx.full_text = "# Repo Context\n\n" + "\n\n".join(sections)
    typer.echo(
        f"[lead] gathered {len(sections)} context section(s) ({len(lead_ctx.full_text)} chars)",
        err=True,
    )
    return lead_ctx


def _compute_readiness_safe(
    repo_path: Path,
) -> tuple[list[str], list[dict[str, str | list[str]]]]:
    """Call compute_readiness, returning empty results on any failure."""
    try:
        from action_harness.prerequisites import compute_readiness

        return compute_readiness(repo_path)
    except Exception:  # noqa: BLE001 — optional context, must not block lead
        return ([], [])


def _build_active_names(
    ready_names: list[str],
    blocked_list: list[dict[str, str | list[str]]],
) -> list[str]:
    """Combine ready + blocked names into a single active changes list."""
    blocked_names: list[str] = []
    for b in blocked_list:
        if isinstance(b, dict):
            name = b.get("name")
            if isinstance(name, str):
                blocked_names.append(name)
    return list(ready_names) + blocked_names


# ---------------------------------------------------------------------------
# Greeting builder
# ---------------------------------------------------------------------------


def build_greeting(ctx: LeadContext) -> str:
    """Build a deterministic greeting prompt from gathered context.

    Produces a concise message the lead agent can use as a starting point
    instead of synthesizing one from the system prompt alone.
    """
    parts: list[str] = [f"You are leading {ctx.repo_name}."]

    if ctx.active_changes:
        parts.append(f"Active changes: {', '.join(ctx.active_changes)}.")

    if ctx.ready_changes:
        parts.append(f"Ready to implement: {', '.join(ctx.ready_changes)}.")

    if ctx.recent_run_stats is not None:
        passed, total = ctx.recent_run_stats
        parts.append(f"Recent runs: {passed}/{total} passed.")

    parts.append("Greet me with a brief status summary and suggest 2-3 directions we could go.")

    greeting = " ".join(parts)
    typer.echo(f"[lead] built greeting ({len(greeting)} chars)", err=True)
    return greeting


# ---------------------------------------------------------------------------
# Lead dispatch
# ---------------------------------------------------------------------------


def dispatch_lead_interactive(
    repo_path: Path,
    prompt: str | None,
    context: LeadContext,
    harness_agents_dir: Path,
    permission_mode: str = "default",
) -> int:
    """Dispatch the lead agent as an interactive Claude Code session.

    Spawns ``claude`` with the lead persona as ``--system-prompt``
    and gathered repo context as ``--append-system-prompt``.

    When *prompt* is provided, it is passed as a positional argument so the
    conversation starts with that message. When *prompt* is ``None``, a
    deterministic greeting built from the gathered context is used instead.

    Uses subprocess.run with inherited stdio (no capture_output) so the human
    can interact naturally with the Claude Code session.

    Returns the exit code from the Claude Code process.
    """
    typer.echo(
        f"[lead] dispatching interactive lead session (repo={repo_path})",
        err=True,
    )

    try:
        persona = load_agent_prompt("lead", repo_path, harness_agents_dir)
    except FileNotFoundError as exc:
        typer.echo(f"[lead] agent file not found: {exc}", err=True)
        return 1

    cmd = [
        "claude",
        "--system-prompt",
        persona,
        "--append-system-prompt",
        context.full_text,
        "--permission-mode",
        permission_mode,
    ]

    # When the user explicitly provides a prompt, use it as-is.
    # Otherwise, build a deterministic greeting from the gathered context.
    if prompt is not None and prompt.strip():
        cmd.insert(1, prompt)
    else:
        greeting = build_greeting(context)
        cmd.insert(1, greeting)

    prompt_label = "<prompt> " if prompt else ""
    typer.echo(
        f"[lead] cmd: claude {prompt_label}--system-prompt <persona>"
        f" --append-system-prompt <context> --permission-mode {permission_mode}",
        err=True,
    )

    start_time = time.monotonic()

    try:
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            timeout=7200,
        )
    except subprocess.TimeoutExpired:
        duration = time.monotonic() - start_time
        typer.echo(
            f"[lead] interactive session timed out after 7200s ({duration:.0f}s)",
            err=True,
        )
        return 1
    except (FileNotFoundError, OSError) as exc:
        typer.echo(f"[lead] failed to launch claude CLI: {exc}", err=True)
        return 1

    duration = time.monotonic() - start_time
    typer.echo(
        f"[lead] interactive session ended (exit={result.returncode}) in {duration:.1f}s",
        err=True,
    )
    return result.returncode


def dispatch_lead(
    repo_path: Path,
    prompt: str,
    context: str,
    harness_agents_dir: Path,
    max_turns: int = 50,
    permission_mode: str = "default",
) -> str:
    """Dispatch the lead agent via Claude Code CLI.

    Loads the lead persona, builds system/user prompts, and dispatches.
    Returns the raw JSON output string from the CLI.
    """
    typer.echo(
        f"[lead] dispatching lead agent (repo={repo_path}, max_turns={max_turns})",
        err=True,
    )

    try:
        persona = load_agent_prompt("lead", repo_path, harness_agents_dir)
    except FileNotFoundError as exc:
        typer.echo(f"[lead] agent file not found: {exc}", err=True)
        return json.dumps({"error": f"Lead agent file not found: {exc}"})
    system_prompt = persona
    user_prompt = f"{context}\n\n## Your Task\n\n{prompt}"

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

    start_time = time.monotonic()

    try:
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=7200,
        )
    except subprocess.TimeoutExpired:
        duration = time.monotonic() - start_time
        typer.echo("[lead] timed out after 7200s", err=True)
        msg = f"Claude CLI timed out after 7200s (duration: {duration:.0f}s)"
        return json.dumps({"error": msg})
    except (FileNotFoundError, OSError) as exc:
        duration = time.monotonic() - start_time
        typer.echo(f"[lead] failed to launch claude CLI: {exc}", err=True)
        return json.dumps({"error": f"Failed to launch claude CLI: {exc}"})

    duration = time.monotonic() - start_time

    if result.returncode != 0:
        typer.echo(
            f"[lead] claude CLI exited with code {result.returncode} in {duration:.1f}s",
            err=True,
        )
        return json.dumps(
            {"error": f"Claude CLI exited with code {result.returncode}: {result.stderr[:500]}"}
        )

    typer.echo(f"[lead] dispatch completed in {duration:.1f}s", err=True)
    return result.stdout


# ---------------------------------------------------------------------------
# Plan parsing
# ---------------------------------------------------------------------------


def parse_lead_plan(raw_output: str) -> LeadPlan:
    """Parse the lead agent's output into a LeadPlan.

    Extracts JSON from the Claude CLI JSON envelope's ``result`` field.
    Returns a default empty LeadPlan if parsing fails (logs warning, never crashes).
    """
    typer.echo("[lead] parsing lead plan from output", err=True)

    try:
        output_data = json.loads(raw_output)
        result_text = output_data.get("result", "")
    except (json.JSONDecodeError, TypeError):
        typer.echo(
            "[lead] warning: could not parse CLI output as JSON, treating as raw text",
            err=True,
        )
        typer.echo(f"[lead] raw output: {raw_output[:500]}", err=True)
        return LeadPlan()

    if not result_text:
        typer.echo("[lead] warning: empty result field in CLI output", err=True)
        return LeadPlan()

    plan_data = extract_json_block(result_text)
    if plan_data is None:
        typer.echo(
            "[lead] warning: no JSON block found in lead output, displaying raw text",
            err=True,
        )
        typer.echo(f"[lead] raw result: {result_text[:1000]}", err=True)
        return LeadPlan(summary=result_text[:500])

    try:
        plan = LeadPlan.model_validate(plan_data)
    except Exception as exc:  # noqa: BLE001 — broad catch intentional:
        # model_validate can raise ValidationError, but also TypeError or
        # other exceptions from malformed agent output. The lead must never
        # crash on bad plan data — return an empty plan and log.
        typer.echo(
            f"[lead] warning: could not validate plan data: {exc}",
            err=True,
        )
        return LeadPlan()

    typer.echo(
        f"[lead] parsed plan: {len(plan.proposals)} proposals, "
        f"{len(plan.issues)} issues, {len(plan.dispatches)} dispatches",
        err=True,
    )
    return plan
