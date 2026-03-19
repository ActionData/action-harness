"""Claude Code skill discovery and injection into target repo worktrees."""

import importlib.resources
import shutil
from pathlib import Path

import typer

SKILL_FILENAME = "SKILL.md"
INJECTED_MARKER = ".harness-injected"


def resolve_harness_skills_dir() -> Path:
    """Resolve the path to the harness's Claude Code skills directory.

    Walks up from this file to find `skills/` in the plugin root.
    Falls back to importlib.resources for installed-as-package support.
    """
    current = Path(__file__).resolve().parent
    # Cap at 10 levels — sufficient for any reasonable repo layout
    # (src/action_harness/ is typically 2–3 levels deep).
    for _ in range(10):
        candidate = current / "skills"
        if candidate.is_dir():
            typer.echo(
                f"[skills] resolved harness skills dir (source): {candidate}",
                err=True,
            )
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent

    # Fallback: installed package
    pkg_path = importlib.resources.files("action_harness") / "default_skills"
    resolved = Path(str(pkg_path))
    if not resolved.is_dir():
        typer.echo(
            f"[skills] warning: package fallback skills dir does not exist: {resolved}. "
            f"Skill files may be missing from the installation.",
            err=True,
        )
    else:
        typer.echo(
            f"[skills] resolved harness skills dir (package): {resolved}",
            err=True,
        )
    return resolved


def discover_skills(skills_dir: Path) -> list[str]:
    """Scan a directory for subdirectories containing SKILL.md.

    Returns sorted list of skill directory names. Returns empty list
    if the directory doesn't exist or can't be read.
    """
    typer.echo(f"[skills] discovering skills in {skills_dir}", err=True)
    if not skills_dir.is_dir():
        typer.echo(f"[skills] skills dir does not exist: {skills_dir}", err=True)
        return []

    found: list[str] = []
    try:
        for entry in skills_dir.iterdir():
            if entry.is_dir() and (entry / SKILL_FILENAME).is_file():
                found.append(entry.name)
    except OSError as exc:
        typer.echo(
            f"[skills] warning: error scanning {skills_dir}: {exc}",
            err=True,
        )
        return []

    found.sort()
    typer.echo(f"[skills] discovered {len(found)} skill(s): {found}", err=True)
    return found


def inject_skills(
    source_dir: Path,
    worktree_path: Path,
    verbose: bool = False,
) -> list[str]:
    """Copy harness skills into a target worktree's .claude/skills/ directory.

    Skips any skill directory that already exists in the target (target repo
    skills take precedence). Writes a .harness-injected marker listing
    injected skill names. Idempotent — safe to call multiple times on the
    same worktree (existing dirs are skipped, gitignore deduplicates).

    Returns list of injected skill names. Returns empty list on errors
    (non-fatal — the worker can still run without skills).
    """
    typer.echo(
        f"[skills] injecting skills from {source_dir} into {worktree_path}",
        err=True,
    )

    skills = discover_skills(source_dir)
    if not skills:
        typer.echo("[skills] no skills to inject", err=True)
        return []

    target_skills_dir = worktree_path / ".claude" / "skills"

    try:
        target_skills_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        typer.echo(
            f"[skills] warning: could not create target skills dir {target_skills_dir}: {exc}",
            err=True,
        )
        return []

    injected: list[str] = []
    for skill_name in skills:
        target_skill = target_skills_dir / skill_name
        if target_skill.exists():
            if verbose:
                typer.echo(
                    f"  skipping '{skill_name}' (exists in target repo)",
                    err=True,
                )
            continue

        source_skill = source_dir / skill_name
        try:
            shutil.copytree(str(source_skill), str(target_skill))
            injected.append(skill_name)
            if verbose:
                typer.echo(f"  injected '{skill_name}'", err=True)
        except OSError as exc:
            typer.echo(
                f"[skills] warning: failed to copy skill '{skill_name}': {exc}",
                err=True,
            )

    # Write marker file and .gitignore to prevent injected skills from
    # being committed to the target repo by workers running `git add`.
    if injected:
        marker_path = target_skills_dir / INJECTED_MARKER
        gitignore_path = target_skills_dir / ".gitignore"
        gitignore_entries = [INJECTED_MARKER] + [f"{s}/" for s in injected]
        try:
            marker_path.write_text(
                "\n".join(injected) + "\n",
                encoding="utf-8",
            )
            # Only write .gitignore if we created it (don't clobber existing)
            if not gitignore_path.exists():
                gitignore_path.write_text(
                    "# Harness-injected skills — do not commit\n"
                    + "\n".join(gitignore_entries)
                    + "\n",
                    encoding="utf-8",
                )
            else:
                # Append entries not already present (line-by-line to
                # avoid substring false positives like "foo/" matching
                # "foobar/").
                existing = gitignore_path.read_text(encoding="utf-8")
                existing_lines = set(existing.splitlines())
                new_entries = [e for e in gitignore_entries if e not in existing_lines]
                if new_entries:
                    gitignore_path.write_text(
                        existing.rstrip("\n")
                        + "\n# Harness-injected skills — do not commit\n"
                        + "\n".join(new_entries)
                        + "\n",
                        encoding="utf-8",
                    )
        except (OSError, UnicodeDecodeError) as exc:
            typer.echo(
                f"[skills] warning: could not write marker/gitignore: {exc}",
                err=True,
            )

    typer.echo(
        f"[skills] injection complete: {len(injected)} skill(s) injected, "
        f"{len(skills) - len(injected)} skipped",
        err=True,
    )
    return injected
