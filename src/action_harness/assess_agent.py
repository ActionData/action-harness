"""Assessment agent dispatch — read-only Claude Code worker for quality judgment."""

import json
import subprocess
import time
from pathlib import Path

import typer

from action_harness.assessment import CategoryScore, Gap


def build_system_prompt() -> str:
    """Build the system prompt for the assessment agent."""
    return """You are a codebase quality assessor. You have read-only access to the repository.

Your task is to evaluate the quality of this codebase for autonomous agent work.
You will receive mechanical scan results as JSON. Your job is to assess quality
beyond what mechanical checks can detect — test quality, documentation clarity,
architecture legibility, CI comprehensiveness, etc.

Output ONLY a JSON object with this exact schema:

{
  "categories": {
    "ci_guardrails": {
      "score_adjustment": <int between -20 and +20>,
      "rationale": "<string explaining the adjustment>",
      "gaps": [{"severity": "high"|"medium"|"low", "finding": "<description>", "proposal_name": "<kebab-case>"|null}]
    },
    "testability": { ... same structure ... },
    "context": { ... same structure ... },
    "tooling": { ... same structure ... },
    "observability": { ... same structure ... },
    "isolation": { ... same structure ... }
  }
}

Guidelines:
- score_adjustment: How many points to add/subtract from the mechanical score.
  Positive = quality better than signals suggest. Negative = quality worse.
  Must be between -20 and +20.
- rationale: Brief explanation of why you're adjusting.
- gaps: Additional gaps you found that mechanical scans missed.
- Read actual source files, test files, and documentation to judge quality.
- Focus on what matters for autonomous agent work.

Output ONLY valid JSON. No markdown, no explanation outside the JSON."""


def build_user_prompt(mechanical_signals: dict[str, object]) -> str:
    """Build the user prompt with mechanical signals."""
    return f"""Assess this repository's quality for autonomous agent work.

Here are the mechanical scan results:

{json.dumps(mechanical_signals, indent=2)}

Read the actual files in this repository to judge quality beyond these signals.
Focus on: test quality, documentation clarity, CI comprehensiveness, and
architecture legibility.

Output your assessment as the JSON schema described in your instructions."""


def dispatch_readonly_worker(
    prompt: str,
    system_prompt: str,
    worktree_path: Path,
    max_turns: int = 50,
    model: str | None = None,
    permission_mode: str = "bypassPermissions",
    verbose: bool = False,
) -> dict[str, object] | None:
    """Dispatch a read-only Claude Code worker.

    Unlike dispatch_worker, this function:
    - Restricts tools to Read, Glob, Grep, Bash
    - Does NOT check for commits
    - Returns parsed JSON output or None on failure
    """
    typer.echo("[assess_agent] dispatching read-only worker", err=True)

    cmd = [
        "claude",
        "-p",
        prompt,
        "--system-prompt",
        system_prompt,
        "--output-format",
        "json",
        "--max-turns",
        str(max_turns),
        "--permission-mode",
        permission_mode,
        "--allowedTools",
        "Read,Glob,Grep,Bash",
    ]

    if model is not None:
        cmd.extend(["--model", model])

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
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        typer.echo("[assess_agent] worker timed out", err=True)
        return None
    except FileNotFoundError:
        typer.echo("[assess_agent] claude CLI not found", err=True)
        return None

    duration = time.monotonic() - start_time
    typer.echo(f"[assess_agent] worker completed in {duration:.1f}s", err=True)

    if result.returncode != 0:
        typer.echo(
            f"[assess_agent] worker failed (exit {result.returncode}): {result.stderr[:200]}",
            err=True,
        )
        return None

    # Parse JSON output from Claude CLI
    if not result.stdout:
        typer.echo("[assess_agent] no output from worker", err=True)
        return None

    try:
        output_data = json.loads(result.stdout)
        worker_result = output_data.get("result", "")

        # The worker result may be a string containing JSON
        if isinstance(worker_result, str):
            # Try to extract JSON from the result string
            # Look for the JSON object in the output
            json_start = worker_result.find("{")
            json_end = worker_result.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                assessment_json = json.loads(worker_result[json_start:json_end])
                return assessment_json

        typer.echo("[assess_agent] could not parse agent output as JSON", err=True)
        return None

    except json.JSONDecodeError as exc:
        typer.echo(f"[assess_agent] JSON parse error: {exc}", err=True)
        return None


def merge_agent_results(
    categories: dict[str, CategoryScore],
    agent_results: dict[str, object],
) -> dict[str, CategoryScore]:
    """Merge agent assessment results with mechanical scores.

    For each category, adds score_adjustment (clamped to ±20), populates
    agent_assessment with rationale, and appends agent-identified gaps.
    """
    agent_categories = agent_results.get("categories")
    if not isinstance(agent_categories, dict):
        typer.echo("[assess_agent] agent output missing 'categories' key", err=True)
        return categories

    for cat_name, cat_score in categories.items():
        agent_cat = agent_categories.get(cat_name)
        if not isinstance(agent_cat, dict):
            continue

        # Get adjustment, clamped to ±20
        raw_adjustment = agent_cat.get("score_adjustment", 0)
        if isinstance(raw_adjustment, int):
            adjustment = max(-20, min(20, raw_adjustment))
        else:
            adjustment = 0

        # Compute new score, clamped to 0-100
        new_score = max(0, min(100, cat_score.score + adjustment))

        # Get rationale
        rationale = agent_cat.get("rationale")
        if not isinstance(rationale, str):
            rationale = None

        # Get agent gaps
        agent_gaps_raw = agent_cat.get("gaps", [])
        agent_gaps: list[Gap] = []
        if isinstance(agent_gaps_raw, list):
            for gap_data in agent_gaps_raw:
                if isinstance(gap_data, dict):
                    try:
                        agent_gaps.append(
                            Gap(
                                severity=gap_data.get("severity", "low"),
                                finding=gap_data.get("finding", ""),
                                category=cat_name,
                                proposal_name=gap_data.get("proposal_name"),
                            )
                        )
                    except (ValueError, KeyError):
                        pass

        # Update category
        categories[cat_name] = CategoryScore(
            score=new_score,
            mechanical_signals=cat_score.mechanical_signals,
            agent_assessment=rationale,
            gaps=cat_score.gaps + agent_gaps,
        )

    return categories


def run_agent_assessment(
    categories: dict[str, CategoryScore],
    repo_path: Path,
) -> dict[str, CategoryScore]:
    """Run the full agent assessment pipeline.

    Dispatches a read-only worker, merges results, and returns updated categories.
    Falls back to mechanical-only scores on any failure.
    """
    # Build mechanical signals dict for the agent
    mechanical_signals: dict[str, object] = {}
    for cat_name, cat_score in categories.items():
        mechanical_signals[cat_name] = {
            "score": cat_score.score,
            "signals": cat_score.mechanical_signals.model_dump(),
        }

    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(mechanical_signals)

    agent_results = dispatch_readonly_worker(
        prompt=user_prompt,
        system_prompt=system_prompt,
        worktree_path=repo_path,
    )

    if agent_results is None:
        typer.echo(
            "[assess_agent] agent assessment failed, using mechanical scores only",
            err=True,
        )
        return categories

    return merge_agent_results(categories, agent_results)
