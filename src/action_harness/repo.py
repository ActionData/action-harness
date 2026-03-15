"""Repository management — clone, fetch, and resolve repo references."""

import re
import shutil
import subprocess
from pathlib import Path

import typer

from action_harness.models import ValidationError


def _detect_gh_protocol() -> str:
    """Detect whether to use HTTPS or SSH for GitHub clones.

    Runs `gh auth token` to check if HTTPS auth is configured.
    Returns "https" if a token exists, "ssh" if not.
    Defaults to "https" if `gh` is not available.
    """
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
        )
        return "https" if result.returncode == 0 else "ssh"
    except FileNotFoundError:
        return "https"


def _parse_repo_ref(repo_arg: str) -> tuple[str, str, str]:
    """Parse a repo reference into (owner, repo_name, clone_url).

    Handles:
    - GitHub shorthand: owner/repo -> https://github.com/owner/repo.git
    - HTTPS URLs: https://github.com/owner/repo[.git]
    - SSH URLs: git@github.com:owner/repo[.git]
    """
    # SSH URL: git@github.com:owner/repo.git
    ssh_match = re.match(r"git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$", repo_arg)
    if ssh_match:
        owner, repo_name = ssh_match.group(1), ssh_match.group(2)
        return owner, repo_name, f"git@github.com:{owner}/{repo_name}.git"

    # HTTPS URL: https://github.com/owner/repo[.git]
    https_match = re.match(r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", repo_arg)
    if https_match:
        owner, repo_name = https_match.group(1), https_match.group(2)
        return owner, repo_name, f"https://github.com/{owner}/{repo_name}.git"

    # GitHub shorthand: owner/repo (exactly one slash, no protocol prefix)
    shorthand_match = re.match(r"^([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$", repo_arg)
    if shorthand_match:
        owner, repo_name = shorthand_match.group(1), shorthand_match.group(2)
        return owner, repo_name, f"https://github.com/{owner}/{repo_name}.git"

    raise ValidationError(f"Cannot parse repo reference: {repo_arg}")


def _is_shorthand(repo_arg: str) -> bool:
    """Return True if repo_arg is GitHub shorthand (owner/repo)."""
    return bool(re.match(r"^([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$", repo_arg))


def _https_to_ssh(https_url: str) -> str:
    """Convert a GitHub HTTPS URL to its SSH equivalent.

    https://github.com/owner/repo.git -> git@github.com:owner/repo.git
    """
    match = re.match(r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", https_url)
    if not match:
        return https_url
    owner, repo_name = match.group(1), match.group(2)
    return f"git@github.com:{owner}/{repo_name}.git"


def _is_https_github_url(url: str) -> bool:
    """Return True if url is an HTTPS GitHub URL."""
    return bool(re.match(r"https?://github\.com/", url))


def _normalize_github_identity(url: str) -> str | None:
    """Extract 'owner/repo' identity from a GitHub URL (HTTPS or SSH).

    Returns None if the URL is not a recognized GitHub URL.
    """
    # HTTPS: https://github.com/owner/repo[.git][/]
    https_match = re.match(r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    if https_match:
        return f"{https_match.group(1)}/{https_match.group(2)}"

    # SSH: git@github.com:owner/repo[.git]
    ssh_match = re.match(r"git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$", url)
    if ssh_match:
        return f"{ssh_match.group(1)}/{ssh_match.group(2)}"

    return None


def _get_repo_dir(owner: str, repo_name: str, clone_url: str, harness_home: Path) -> Path:
    """Return the directory to clone into, handling name collisions.

    Default: harness_home/repos/<repo_name>/
    Collision: harness_home/repos/<owner>-<repo_name>/
    """
    default_dir = harness_home / "repos" / repo_name

    if not default_dir.exists():
        return default_dir

    # Check if existing dir is the same repo
    result = subprocess.run(
        ["git", "-C", str(default_dir), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        existing_url = result.stdout.strip()
        # Protocol-aware comparison: normalize both to owner/repo identity
        # so HTTPS and SSH URLs for the same repo are recognized as equal
        existing_identity = _normalize_github_identity(existing_url)
        clone_identity = _normalize_github_identity(clone_url)
        if existing_identity and clone_identity and existing_identity == clone_identity:
            return default_dir
        # Fall back to exact match for non-GitHub URLs
        if existing_url == clone_url:
            return default_dir

    # Collision — use owner-repo
    fallback_dir = harness_home / "repos" / f"{owner}-{repo_name}"
    typer.echo(
        f"[repo] name collision: {repo_name} already exists with different origin, "
        f"using {fallback_dir.name}",
        err=True,
    )
    return fallback_dir


def _clone_or_fetch(clone_url: str, repo_dir: Path, verbose: bool) -> None:
    """Clone a repo or fetch if already cloned.

    Raises ValidationError if clone fails.
    """
    if not repo_dir.exists():
        typer.echo(f"[repo] cloning {clone_url} to {repo_dir}", err=True)
        result = subprocess.run(
            ["git", "clone", clone_url, str(repo_dir)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            # Fallback: if HTTPS GitHub URL failed, try SSH
            if _is_https_github_url(clone_url):
                ssh_url = _https_to_ssh(clone_url)
                typer.echo(
                    f"[repo] HTTPS clone failed, falling back to SSH: {ssh_url}",
                    err=True,
                )
                # Clean up partial clone directory before retrying
                if repo_dir.exists():
                    shutil.rmtree(repo_dir)
                ssh_result = subprocess.run(
                    ["git", "clone", ssh_url, str(repo_dir)],
                    capture_output=True,
                    text=True,
                )
                if ssh_result.returncode != 0:
                    raise ValidationError(
                        f"Failed to clone {clone_url} (HTTPS: {result.stderr.strip()}) "
                        f"and {ssh_url} (SSH: {ssh_result.stderr.strip()})"
                    )
                # Update remote URL to SSH so collision detection works next run
                set_url_result = subprocess.run(
                    ["git", "-C", str(repo_dir), "remote", "set-url", "origin", ssh_url],
                    capture_output=True,
                    text=True,
                )
                if set_url_result.returncode != 0:
                    typer.echo(
                        f"[repo] warning: failed to update remote URL: "
                        f"{set_url_result.stderr.strip()}",
                        err=True,
                    )
                if verbose:
                    typer.echo("  clone complete (SSH fallback)", err=True)
            else:
                raise ValidationError(f"Failed to clone {clone_url}: {result.stderr.strip()}")
        elif verbose:
            typer.echo("  clone complete", err=True)
    else:
        typer.echo(f"[repo] fetching origin in {repo_dir}", err=True)
        result = subprocess.run(
            ["git", "fetch", "origin"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            typer.echo(f"[repo] warning: fetch failed: {result.stderr.strip()}", err=True)
        elif verbose:
            typer.echo("  fetch complete", err=True)


def resolve_repo(repo_arg: str, harness_home: Path, verbose: bool = False) -> tuple[Path, str]:
    """Resolve a --repo argument to (local_path, repo_name).

    If repo_arg is an existing local directory, return it directly.
    If it's a GitHub shorthand, HTTPS URL, or SSH URL, clone or locate
    the repo under harness_home/repos/ and return the clone path.

    Raises ValidationError if the repo cannot be resolved or cloned.
    """
    # Local path — existing directory
    local_path = Path(repo_arg)
    if local_path.is_dir():
        return local_path.resolve(), local_path.resolve().name

    # Remote reference — parse, locate/clone, return
    owner, repo_name, clone_url = _parse_repo_ref(repo_arg)

    # For shorthand input, detect auth protocol and swap URL if needed
    if _is_shorthand(repo_arg):
        protocol = _detect_gh_protocol()
        if protocol == "ssh":
            clone_url = _https_to_ssh(clone_url)

    repo_dir = _get_repo_dir(owner, repo_name, clone_url, harness_home)

    # Ensure repos directory exists
    repo_dir.parent.mkdir(parents=True, exist_ok=True)

    _clone_or_fetch(clone_url, repo_dir, verbose)

    # Use repo_dir.name (not repo_name) so collision fallback (owner-repo) is reflected
    return repo_dir, repo_dir.name
