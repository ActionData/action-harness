"""Lead registry: identity, state persistence, locking, and clone provisioning."""

from __future__ import annotations

import os
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

import typer
import yaml
from pydantic import BaseModel, ValidationError

# ---------------------------------------------------------------------------
# LeadState model (task 1.1)
# ---------------------------------------------------------------------------


class LeadState(BaseModel):
    """Persistent state for a named lead agent."""

    name: str
    repo_name: str
    purpose: str
    created_at: str
    last_active: str
    session_id: str
    clone_path: str | None
    repo_path: str


# ---------------------------------------------------------------------------
# Repo-name derivation (task 1.2)
# ---------------------------------------------------------------------------


def derive_repo_name(repo_path: Path, harness_home: Path) -> str:
    """Derive a stable repo name for lead storage paths.

    Strategy:
    1. If the repo is managed (under harness_home/projects/<name>/repo/), use <name>.
    2. Extract from ``git remote get-url origin`` (last path component, stripped of .git).
    3. Fall back to the directory basename.
    """
    # Deferred import to avoid circular dependency: cli.py imports lead_registry
    from action_harness.cli import is_managed_repo

    # (1) Managed repo
    if is_managed_repo(repo_path, harness_home):
        # Path is harness_home / "projects" / <name> / "repo" / ...
        # The project name is the parent of "repo"
        try:
            relative = repo_path.resolve().relative_to(harness_home.resolve() / "projects")
            # relative is like <name>/repo or <name>/repo/subdir
            project_name = relative.parts[0]
            typer.echo(
                f"[lead-registry] derive_repo_name: managed repo -> {project_name}",
                err=True,
            )
            return project_name
        except (ValueError, IndexError):
            pass

    # (2) Git remote
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0 and result.stdout.strip():
            url = result.stdout.strip().rstrip("/")
            # Handle both SSH (git@...:org/repo.git) and HTTPS URLs
            if ":" in url and not url.startswith(("http://", "https://")):
                # SSH format: git@github.com:org/repo.git
                url = url.split(":")[-1]
            name = url.split("/")[-1]
            if name.endswith(".git"):
                name = name[:-4]
            if name:
                typer.echo(
                    f"[lead-registry] derive_repo_name: git remote -> {name}",
                    err=True,
                )
                return name
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        typer.echo(
            f"[lead-registry] derive_repo_name: git remote failed: {exc}",
            err=True,
        )

    # (3) Fallback to directory basename
    fallback = repo_path.name
    typer.echo(
        f"[lead-registry] derive_repo_name: fallback to basename -> {fallback}",
        err=True,
    )
    return fallback


# ---------------------------------------------------------------------------
# State directory (task 1.3)
# ---------------------------------------------------------------------------


def lead_state_dir(harness_home: Path, repo_name: str, lead_name: str) -> Path:
    """Return the state directory path for a lead. Does NOT create it."""
    return harness_home / "leads" / repo_name / lead_name


# ---------------------------------------------------------------------------
# State persistence (tasks 1.4, 1.5, 1.6)
# ---------------------------------------------------------------------------


def save_lead_state(state: LeadState, harness_home: Path) -> Path:
    """Save lead state to lead.yaml. Returns the path to the file."""
    state_dir = lead_state_dir(harness_home, state.repo_name, state.name)
    state_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = state_dir / "lead.yaml"
    try:
        yaml_path.write_text(
            yaml.dump(state.model_dump(), default_flow_style=False),
            encoding="utf-8",
        )
    except OSError as exc:
        raise RuntimeError(f"Failed to write lead state to {yaml_path}: {exc}") from exc
    return yaml_path


def load_lead_state(harness_home: Path, repo_name: str, lead_name: str) -> LeadState | None:
    """Load lead state from lead.yaml. Returns None if not found or on error."""
    yaml_path = lead_state_dir(harness_home, repo_name, lead_name) / "lead.yaml"
    if not yaml_path.is_file():
        return None
    try:
        raw = yaml_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
        return LeadState.model_validate(data)
    except (OSError, UnicodeDecodeError, yaml.YAMLError, ValidationError) as exc:
        typer.echo(
            f"[lead-registry] warning: could not load lead state from {yaml_path}: {exc}",
            err=True,
        )
        return None


def list_leads(harness_home: Path, repo_name: str) -> list[LeadState]:
    """List all leads for a repo. Returns empty list if none exist."""
    repo_dir = harness_home / "leads" / repo_name
    if not repo_dir.is_dir():
        return []
    states: list[LeadState] = []
    for child in sorted(repo_dir.iterdir()):
        if child.is_dir():
            state = load_lead_state(harness_home, repo_name, child.name)
            if state is not None:
                states.append(state)
    return states


# ---------------------------------------------------------------------------
# Resolve or create (task 1.7)
# ---------------------------------------------------------------------------


def resolve_or_create_lead(
    harness_home: Path,
    repo_path: Path,
    lead_name: str,
    purpose: str,
    provision_clone_flag: bool = False,
) -> LeadState:
    """Resolve an existing lead or create a new one.

    Returns the LeadState (saved to disk). When *provision_clone_flag* is True
    and the lead is not the default, a full git clone is provisioned.
    """
    repo_name = derive_repo_name(repo_path, harness_home)
    existing = load_lead_state(harness_home, repo_name, lead_name)

    if existing is not None:
        typer.echo(
            f"[lead-registry] resolve_or_create_lead: existing lead '{lead_name}'",
            err=True,
        )
        existing.last_active = datetime.now(UTC).isoformat()
        save_lead_state(existing, harness_home)
        return existing

    # Create new lead
    now = datetime.now(UTC).isoformat()
    state = LeadState(
        name=lead_name,
        repo_name=repo_name,
        purpose=purpose,
        created_at=now,
        last_active=now,
        session_id=str(uuid.uuid4()),
        clone_path=None,
        repo_path=str(repo_path.resolve()),
    )
    save_lead_state(state, harness_home)
    typer.echo(
        f"[lead-registry] resolve_or_create_lead: created lead '{lead_name}' "
        f"(session_id={state.session_id})",
        err=True,
    )

    # Provision clone for named (non-default) leads
    if provision_clone_flag and lead_name != "default":
        try:
            clone_path = provision_clone(state, harness_home)
            state.clone_path = str(clone_path)
            save_lead_state(state, harness_home)
        except RuntimeError as exc:
            typer.echo(
                f"[lead-registry] warning: clone provisioning failed: {exc}",
                err=True,
            )
            # clone_path remains None — will be retried on next start

    return state


# ---------------------------------------------------------------------------
# Lock management (tasks 2.1, 2.2, 2.3)
# ---------------------------------------------------------------------------


def acquire_lock(
    harness_home: Path,
    repo_name: str,
    lead_name: str,
    pid: int,
    session_id: str,
) -> None:
    """Acquire the lead lock. Raises RuntimeError if already held by a live process.

    Note: This uses a check-then-write pattern which has a small TOCTOU race window.
    Two processes starting within milliseconds could both acquire the lock. Acceptable
    for the current use case (human-initiated terminal sessions). If stronger guarantees
    are needed, switch to os.open(O_CREAT|O_EXCL) or fcntl.flock.
    """
    lock_path = lead_state_dir(harness_home, repo_name, lead_name) / "lock"

    if lock_path.is_file():
        try:
            content = lock_path.read_text(encoding="utf-8")
            lines = content.strip().split("\n")
            existing_pid = int(lines[0])
            # Check if process is alive via signal 0 (no-op signal).
            # Known limitation: PID reuse could cause false positives on
            # long-lived systems, but rare with 32-bit PID spaces.
            try:
                os.kill(existing_pid, 0)
                # Process is alive — refuse
                raise RuntimeError(f"Lead '{lead_name}' is already running (PID {existing_pid})")
            except OSError:
                # Process is dead — stale lock
                typer.echo(
                    f"[lead-registry] warning: reclaiming stale lock for '{lead_name}' "
                    f"(dead PID {existing_pid})",
                    err=True,
                )
        except (ValueError, IndexError):
            typer.echo(
                f"[lead-registry] warning: corrupt lock file for '{lead_name}', reclaiming",
                err=True,
            )

    # Write new lock
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(f"{pid}\n{session_id}\n", encoding="utf-8")


def release_lock(harness_home: Path, repo_name: str, lead_name: str) -> None:
    """Release the lead lock. Never raises — safe for finally blocks."""
    lock_path = lead_state_dir(harness_home, repo_name, lead_name) / "lock"
    try:
        if lock_path.is_file():
            lock_path.unlink()
    except OSError as exc:
        typer.echo(
            f"[lead-registry] warning: could not release lock for '{lead_name}': {exc}",
            err=True,
        )


def is_lead_active(harness_home: Path, repo_name: str, lead_name: str) -> bool:
    """Check if a lead is currently active (lock held by a live process).

    Side effect: cleans up stale lock files (dead PID). This has its own
    small TOCTOU window — acceptable for the same reasons as acquire_lock.
    """
    lock_path = lead_state_dir(harness_home, repo_name, lead_name) / "lock"
    if not lock_path.is_file():
        return False
    try:
        content = lock_path.read_text(encoding="utf-8")
        lines = content.strip().split("\n")
        existing_pid = int(lines[0])
        try:
            os.kill(existing_pid, 0)
            return True
        except OSError:
            # Dead process — clean up stale lock
            try:
                lock_path.unlink()
            except OSError:
                pass
            return False
    except (ValueError, IndexError, OSError):
        return False


# ---------------------------------------------------------------------------
# Clone provisioning (task 3.1)
# ---------------------------------------------------------------------------


def _ensure_harness_managed_marker(clone_dir: Path) -> None:
    """Create the .harness-managed marker if it doesn't already exist."""
    marker_path = clone_dir / ".harness-managed"
    if marker_path.exists():
        return
    try:
        marker_path.write_text(
            "This clone is managed by the action-harness lead registry.\n",
            encoding="utf-8",
        )
    except OSError as exc:
        typer.echo(
            f"[lead-registry] provision_clone: warning: could not create marker: {exc}",
            err=True,
        )


def provision_clone(state: LeadState, harness_home: Path) -> Path:
    """Provision a full git clone for a named lead.

    Returns the clone directory path. Skips if clone already exists.
    """
    clone_dir = lead_state_dir(harness_home, state.repo_name, state.name) / "clone"

    if clone_dir.is_dir():
        typer.echo(
            f"[lead-registry] provision_clone: clone already exists at {clone_dir}",
            err=True,
        )
        # Ensure marker exists even for clones created before this feature
        _ensure_harness_managed_marker(clone_dir)
        return clone_dir

    # Determine clone source: prefer remote URL over local path
    source = state.repo_path
    try:
        result = subprocess.run(
            ["git", "-C", state.repo_path, "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0 and result.stdout.strip():
            source = result.stdout.strip()
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        pass

    typer.echo(
        f"[lead-registry] provision_clone: cloning from {source} to {clone_dir}",
        err=True,
    )

    try:
        clone_result = subprocess.run(
            ["git", "clone", source, str(clone_dir)],
            capture_output=True,
            text=True,
            timeout=600,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Failed to clone from {source} to {clone_dir}: {exc}") from exc

    if clone_result.returncode != 0:
        raise RuntimeError(
            f"git clone failed (exit {clone_result.returncode}): {clone_result.stderr.strip()}"
        )

    # Create .harness-managed marker so /sync can detect harness-owned clones
    _ensure_harness_managed_marker(clone_dir)

    typer.echo(
        f"[lead-registry] provision_clone: clone complete at {clone_dir}",
        err=True,
    )
    return clone_dir


# ---------------------------------------------------------------------------
# Repo sync
# ---------------------------------------------------------------------------


def _get_default_branch(repo_path: Path) -> str | None:
    """Return the default branch name (e.g., 'main') from origin HEAD, or None."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "symbolic-ref", "refs/remotes/origin/HEAD"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            # refs/remotes/origin/main -> main
            return result.stdout.strip().split("/")[-1]
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        pass
    return None


def sync_repo(repo_path: Path, *, is_clone: bool) -> None:
    """Fetch origin and update the working tree to the latest default branch.

    For harness-owned clones (``is_clone=True``): hard-resets to
    ``origin/<default-branch>`` so the clone always reflects remote HEAD.

    For user working trees (``is_clone=False``): fetches only. Logs a
    warning if the local branch is behind origin but does not modify
    the working tree.

    Never raises — sync failures are logged and must not block the lead.
    """
    typer.echo(f"[lead-registry] sync_repo: syncing {repo_path}", err=True)

    # Fetch origin
    try:
        fetch_result = subprocess.run(
            ["git", "-C", str(repo_path), "fetch", "origin"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if fetch_result.returncode != 0:
            typer.echo(
                f"[lead-registry] sync_repo: warning: git fetch failed: "
                f"{fetch_result.stderr.strip()[:200]}",
                err=True,
            )
            return
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        typer.echo(
            f"[lead-registry] sync_repo: warning: git fetch failed: {exc}",
            err=True,
        )
        return

    default_branch = _get_default_branch(repo_path)
    if default_branch is None:
        typer.echo(
            "[lead-registry] sync_repo: warning: could not determine default branch "
            "(try: git remote set-head origin --auto)",
            err=True,
        )
        return

    if is_clone:
        # Hard-reset clone to latest remote state
        try:
            reset_result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo_path),
                    "reset",
                    "--hard",
                    f"origin/{default_branch}",
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if reset_result.returncode != 0:
                typer.echo(
                    f"[lead-registry] sync_repo: warning: git reset failed: "
                    f"{reset_result.stderr.strip()[:200]}",
                    err=True,
                )
            else:
                typer.echo(
                    f"[lead-registry] sync_repo: synced clone to origin/{default_branch}",
                    err=True,
                )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
            typer.echo(
                f"[lead-registry] sync_repo: warning: git reset failed: {exc}",
                err=True,
            )
    else:
        # User working tree — just check if behind
        try:
            behind_result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo_path),
                    "rev-list",
                    "--count",
                    f"HEAD..origin/{default_branch}",
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if behind_result.returncode == 0:
                behind_count = int(behind_result.stdout.strip())
                if behind_count > 0:
                    typer.echo(
                        f"[lead-registry] sync_repo: warning: local branch is "
                        f"{behind_count} commit(s) behind origin/{default_branch}",
                        err=True,
                    )
                else:
                    typer.echo(
                        f"[lead-registry] sync_repo: up to date with origin/{default_branch}",
                        err=True,
                    )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired, ValueError) as exc:
            typer.echo(
                f"[lead-registry] sync_repo: warning: behind-check failed: {exc}",
                err=True,
            )
