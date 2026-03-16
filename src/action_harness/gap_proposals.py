"""Gap proposal generation — create OpenSpec changes for assessment gaps."""

import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import typer

from action_harness.assessment import Gap
from action_harness.profiler import RepoProfile


def _scaffold_change(proposal_name: str, repo_path: Path) -> bool:
    """Create an OpenSpec change directory for a gap proposal."""
    typer.echo(f"[gap_proposals] scaffolding change: {proposal_name}", err=True)
    try:
        result = subprocess.run(
            ["openspec", "new", "change", proposal_name],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            typer.echo(
                f"[gap_proposals] failed to scaffold {proposal_name}: {result.stderr[:200]}",
                err=True,
            )
            return False
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        typer.echo(
            f"[gap_proposals] error scaffolding {proposal_name}: {exc}",
            err=True,
        )
        return False


def _build_spec_writer_prompt(gap: Gap, profile: RepoProfile, claude_md: str | None) -> str:
    """Build the prompt for a spec-writer agent."""
    context_parts = [
        f"Ecosystem: {profile.ecosystem}",
        f"Gap severity: {gap.severity}",
        f"Gap category: {gap.category}",
        f"Gap finding: {gap.finding}",
        f"Proposal name: {gap.proposal_name}",
    ]

    if claude_md:
        context_parts.append(f"\nCLAUDE.md contents:\n{claude_md}")

    return f"""Write a proposal.md for the OpenSpec change '{gap.proposal_name}'.

Repository context:
{chr(10).join(context_parts)}

The proposal should:
1. Explain WHY this gap matters for autonomous agent work
2. Describe WHAT changes are needed
3. List the capabilities being added or modified
4. Identify potential impacts on existing code

Write the proposal.md file at openspec/changes/{gap.proposal_name}/proposal.md"""


def _dispatch_spec_writer(
    gap: Gap,
    repo_path: Path,
    profile: RepoProfile,
    claude_md: str | None,
) -> tuple[str, bool]:
    """Dispatch a single spec-writer agent for a gap.

    Returns (proposal_name, success).
    """
    proposal_name = gap.proposal_name
    if not proposal_name:
        return ("", False)

    typer.echo(f"[gap_proposals] dispatching spec-writer for {proposal_name}", err=True)

    prompt = _build_spec_writer_prompt(gap, profile, claude_md)

    try:
        result = subprocess.run(
            [
                "claude",
                "-p",
                prompt,
                "--output-format",
                "json",
                "--max-turns",
                "20",
                "--permission-mode",
                "bypassPermissions",
                "--allowedTools",
                "Read,Glob,Grep,Edit,Write",
            ],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            typer.echo(f"[gap_proposals] spec-writer completed for {proposal_name}", err=True)
            return (proposal_name, True)
        typer.echo(
            f"[gap_proposals] spec-writer failed for {proposal_name}: exit {result.returncode}",
            err=True,
        )
        return (proposal_name, False)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        typer.echo(
            f"[gap_proposals] spec-writer error for {proposal_name}: {exc}",
            err=True,
        )
        return (proposal_name, False)


def generate_proposals(
    proposals: list[Gap],
    repo_path: Path,
    profile: RepoProfile,
    max_workers: int = 3,
) -> list[tuple[str, bool]]:
    """Generate OpenSpec proposals for identified gaps.

    Scaffolds change directories and dispatches spec-writer agents in parallel.
    Returns list of (proposal_name, success) tuples.
    """
    typer.echo(f"[gap_proposals] generating {len(proposals)} proposals", err=True)

    # Read CLAUDE.md for context
    claude_md: str | None = None
    claude_md_path = repo_path / "CLAUDE.md"
    if claude_md_path.exists():
        try:
            claude_md = claude_md_path.read_text()
        except OSError:
            pass

    # Filter proposals with names
    named_proposals = [p for p in proposals if p.proposal_name]

    if not named_proposals:
        typer.echo("[gap_proposals] no proposals with names to generate", err=True)
        return []

    # Scaffold all change directories first
    for gap in named_proposals:
        if gap.proposal_name:
            _scaffold_change(gap.proposal_name, repo_path)

    # Dispatch spec-writer agents in parallel
    results: list[tuple[str, bool]] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_dispatch_spec_writer, gap, repo_path, profile, claude_md): gap
            for gap in named_proposals
        }

        for future in as_completed(futures):
            gap = futures[future]
            try:
                name, success = future.result()
            except Exception as exc:
                name = gap.proposal_name or ""
                success = False
                typer.echo(
                    f"[gap_proposals] ✗ {name} (unexpected error: {exc})",
                    err=True,
                )
            results.append((name, success))
            if success:
                typer.echo(f"[gap_proposals] ✓ {name}", err=True)
            elif name:
                typer.echo(f"[gap_proposals] ✗ {name} (failed)", err=True)

    succeeded = sum(1 for _, s in results if s)
    typer.echo(
        f"[gap_proposals] done: {succeeded}/{len(results)} proposals generated",
        err=True,
    )
    return results
