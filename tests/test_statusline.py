"""Tests for .harness/statusline.sh — sync status indicator."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

STATUSLINE_SCRIPT = Path(__file__).resolve().parent.parent / ".harness" / "statusline.sh"


def _run_statusline(
    cwd: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the statusline script in the given directory."""
    return subprocess.run(
        ["bash", str(STATUSLINE_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=30,
        env=env,
    )


def _init_repo_with_remote(tmp_path: Path, *, branch: str = "main") -> tuple[Path, Path]:
    """Create a bare remote and a clone, returning (clone_dir, remote_dir)."""
    remote = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", f"--initial-branch={branch}", str(remote)],
        capture_output=True,
        timeout=120,
        check=True,
    )

    clone = tmp_path / "repo"
    subprocess.run(
        ["git", "clone", str(remote), str(clone)],
        capture_output=True,
        timeout=120,
        check=True,
    )

    # Create an initial commit so refs exist
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@test.com",
            "commit",
            "--allow-empty",
            "-m",
            "init",
        ],
        cwd=str(clone),
        capture_output=True,
        timeout=120,
        check=True,
    )
    subprocess.run(
        ["git", "push", "origin", branch],
        cwd=str(clone),
        capture_output=True,
        timeout=120,
        check=True,
    )
    # Set origin/HEAD so default branch detection works
    subprocess.run(
        ["git", "remote", "set-head", "origin", "--auto"],
        cwd=str(clone),
        capture_output=True,
        timeout=120,
        check=True,
    )

    return clone, remote


def _clear_cache(repo_path: Path) -> None:
    """Remove the statusline cache file for the given repo."""
    import hashlib

    repo_root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=str(repo_path),
        capture_output=True,
        text=True,
        timeout=120,
    ).stdout.strip()
    repo_hash = hashlib.sha256(repo_root.encode()).hexdigest()[:12]
    cache_file = Path(f"/tmp/harness-sync-cache-{repo_hash}")
    if cache_file.exists():
        cache_file.unlink()


class TestStatuslineNotGitRepo:
    def test_non_git_directory_produces_no_output(self, tmp_path: Path) -> None:
        """Statusline should silently exit in a non-git directory."""
        result = _run_statusline(str(tmp_path))
        assert result.returncode == 0
        assert result.stdout == ""


class TestStatuslineNoRemote:
    def test_no_remote_produces_no_output(self, tmp_path: Path) -> None:
        """Statusline should silently exit when there is no 'origin' remote."""
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=str(repo), capture_output=True, timeout=120, check=True)

        result = _run_statusline(str(repo))
        assert result.returncode == 0
        assert result.stdout == ""


class TestStatuslineInSync:
    def test_shows_in_sync_when_matching(self, tmp_path: Path) -> None:
        """Statusline shows '✓ in sync' when local matches remote."""
        clone, _remote = _init_repo_with_remote(tmp_path)
        _clear_cache(clone)

        result = _run_statusline(str(clone))
        assert result.returncode == 0
        assert "in sync" in result.stdout


class TestStatuslineBehind:
    def test_shows_behind_when_remote_has_new_commits(self, tmp_path: Path) -> None:
        """Statusline shows 'behind' when remote has commits not fetched locally."""
        clone, remote = _init_repo_with_remote(tmp_path)

        # Push a new commit from a second clone (simulating someone else pushing)
        clone2 = tmp_path / "clone2"
        subprocess.run(
            ["git", "clone", str(remote), str(clone2)],
            capture_output=True,
            timeout=120,
            check=True,
        )
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@test.com",
                "commit",
                "--allow-empty",
                "-m",
                "new commit",
            ],
            cwd=str(clone2),
            capture_output=True,
            timeout=120,
            check=True,
        )
        subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=str(clone2),
            capture_output=True,
            timeout=120,
            check=True,
        )

        _clear_cache(clone)
        result = _run_statusline(str(clone))
        assert result.returncode == 0
        assert "behind" in result.stdout


class TestStatuslineCache:
    def test_cache_file_created(self, tmp_path: Path) -> None:
        """Running statusline creates a cache file in /tmp."""
        import hashlib

        clone, _remote = _init_repo_with_remote(tmp_path)
        _clear_cache(clone)

        _run_statusline(str(clone))

        repo_root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(clone),
            capture_output=True,
            text=True,
            timeout=120,
        ).stdout.strip()
        repo_hash = hashlib.sha256(repo_root.encode()).hexdigest()[:12]
        cache_file = Path(f"/tmp/harness-sync-cache-{repo_hash}")
        assert cache_file.exists()

    def test_cache_prevents_network_call_on_second_run(self, tmp_path: Path) -> None:
        """Second run within TTL should be fast (cache hit)."""
        clone, _remote = _init_repo_with_remote(tmp_path)
        _clear_cache(clone)

        # First run populates cache
        _run_statusline(str(clone))

        # Second run should use cache — measure time as a proxy
        start = time.monotonic()
        result = _run_statusline(str(clone))
        elapsed = time.monotonic() - start

        assert result.returncode == 0
        # Cache hit should be very fast (no network), but we use a generous threshold
        assert elapsed < 2.0

    def test_network_failure_cache_prevents_retry(self, tmp_path: Path) -> None:
        """When network fails, sentinel is cached and prevents retries within TTL."""
        import hashlib

        clone, _remote = _init_repo_with_remote(tmp_path)

        # Simulate network failure by writing a NETWORK_ERROR sentinel to cache
        repo_root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(clone),
            capture_output=True,
            text=True,
            timeout=120,
        ).stdout.strip()
        repo_hash = hashlib.sha256(repo_root.encode()).hexdigest()[:12]
        cache_file = Path(f"/tmp/harness-sync-cache-{repo_hash}")

        now = int(time.time())
        cache_file.write_text(f"{now}\nNETWORK_ERROR\n")

        result = _run_statusline(str(clone))
        assert result.returncode == 0
        assert "sync unknown" in result.stdout


class TestStatuslineDefaultBranchFallback:
    @pytest.mark.skipif(
        not STATUSLINE_SCRIPT.exists(),
        reason="statusline script not found",
    )
    def test_falls_back_to_main(self, tmp_path: Path) -> None:
        """When origin/HEAD is not set, falls back to origin/main."""
        clone, _remote = _init_repo_with_remote(tmp_path)
        _clear_cache(clone)

        # Remove the symbolic-ref so fallback kicks in
        subprocess.run(
            ["git", "remote", "set-head", "origin", "--delete"],
            cwd=str(clone),
            capture_output=True,
            timeout=120,
            check=True,
        )

        result = _run_statusline(str(clone))
        assert result.returncode == 0
        # Should still work via fallback
        assert "in sync" in result.stdout or "behind" in result.stdout

    def test_falls_back_to_master(self, tmp_path: Path) -> None:
        """When origin/HEAD is not set and no origin/main, falls back to origin/master."""
        clone, _remote = _init_repo_with_remote(tmp_path, branch="master")
        _clear_cache(clone)

        # Remove the symbolic-ref so fallback chain kicks in
        subprocess.run(
            ["git", "remote", "set-head", "origin", "--delete"],
            cwd=str(clone),
            capture_output=True,
            timeout=120,
            check=True,
        )

        result = _run_statusline(str(clone))
        assert result.returncode == 0
        assert "in sync" in result.stdout or "behind" in result.stdout
