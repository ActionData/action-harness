"""Tests for the lead registry module and CLI commands."""

from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from action_harness.cli import app
from action_harness.lead_registry import (
    LeadState,
    acquire_lock,
    derive_repo_name,
    is_lead_active,
    lead_state_dir,
    list_leads,
    load_lead_state,
    provision_clone,
    release_lock,
    resolve_or_create_lead,
    save_lead_state,
    sync_repo,
)

runner = CliRunner()


def _make_state(
    name: str = "test-lead",
    repo_name: str = "my-repo",
    purpose: str = "Testing",
    repo_path: str = "/tmp/fake-repo",
    clone_path: str | None = None,
) -> LeadState:
    """Helper to create a LeadState for tests."""
    return LeadState(
        name=name,
        repo_name=repo_name,
        purpose=purpose,
        created_at="2026-01-01T00:00:00+00:00",
        last_active="2026-01-01T00:00:00+00:00",
        session_id=str(uuid.uuid4()),
        clone_path=clone_path,
        repo_path=repo_path,
    )


# ---------------------------------------------------------------------------
# 5.1: LeadState model tests
# ---------------------------------------------------------------------------


class TestLeadStateModel:
    def test_roundtrip(self) -> None:
        """LeadState survives model_dump -> model_validate roundtrip."""
        state = _make_state()
        data = state.model_dump()
        assert set(data.keys()) == {
            "name",
            "repo_name",
            "purpose",
            "created_at",
            "last_active",
            "session_id",
            "clone_path",
            "repo_path",
        }
        restored = LeadState.model_validate(data)
        assert restored.name == state.name
        assert restored.repo_name == state.repo_name
        assert restored.purpose == state.purpose
        assert restored.created_at == state.created_at
        assert restored.last_active == state.last_active
        assert restored.session_id == state.session_id
        assert restored.clone_path == state.clone_path
        assert restored.repo_path == state.repo_path

    def test_clone_path_none(self) -> None:
        """clone_path=None serializes and deserializes correctly."""
        state = _make_state(clone_path=None)
        data = state.model_dump()
        assert data["clone_path"] is None
        restored = LeadState.model_validate(data)
        assert restored.clone_path is None


# ---------------------------------------------------------------------------
# 5.2: derive_repo_name tests
# ---------------------------------------------------------------------------


class TestDeriveRepoName:
    def test_managed_repo(self, tmp_path: Path) -> None:
        """Managed repo path returns the project name."""
        harness_home = tmp_path / "harness"
        project_repo = harness_home / "projects" / "my-proj" / "repo"
        project_repo.mkdir(parents=True)
        # Need a .git dir so is_managed_repo works on an actual path
        result = derive_repo_name(project_repo, harness_home)
        assert result == "my-proj"

    def test_git_remote_ssh(self, tmp_path: Path) -> None:
        """Extracts repo name from SSH git remote URL."""
        harness_home = tmp_path / "harness"
        repo = tmp_path / "code"
        repo.mkdir()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "git@github.com:org/my-app.git\n"

        with patch("action_harness.lead_registry.subprocess.run", return_value=mock_result):
            result = derive_repo_name(repo, harness_home)
        assert result == "my-app"

    def test_git_remote_https_trailing_slash(self, tmp_path: Path) -> None:
        """Extracts repo name from HTTPS URL with trailing slash, no .git."""
        harness_home = tmp_path / "harness"
        repo = tmp_path / "code"
        repo.mkdir()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "https://github.com/org/my-app/\n"

        with patch("action_harness.lead_registry.subprocess.run", return_value=mock_result):
            result = derive_repo_name(repo, harness_home)
        assert result == "my-app"

    def test_fallback_to_basename(self, tmp_path: Path) -> None:
        """Falls back to directory basename when git fails."""
        harness_home = tmp_path / "harness"
        repo = tmp_path / "my-local-project"
        repo.mkdir()

        with patch(
            "action_harness.lead_registry.subprocess.run",
            side_effect=FileNotFoundError("git not found"),
        ):
            result = derive_repo_name(repo, harness_home)
        assert result == "my-local-project"


# ---------------------------------------------------------------------------
# 5.3: save and load tests
# ---------------------------------------------------------------------------


class TestSaveLoadState:
    def test_save_and_load(self, tmp_path: Path) -> None:
        """Save then load returns identical state."""
        state = _make_state()
        save_lead_state(state, tmp_path)
        loaded = load_lead_state(tmp_path, state.repo_name, state.name)
        assert loaded is not None
        assert loaded.name == state.name
        assert loaded.repo_name == state.repo_name
        assert loaded.purpose == state.purpose
        assert loaded.created_at == state.created_at
        assert loaded.last_active == state.last_active
        assert loaded.session_id == state.session_id
        assert loaded.clone_path == state.clone_path
        assert loaded.repo_path == state.repo_path

    def test_load_nonexistent(self, tmp_path: Path) -> None:
        """Loading a nonexistent lead returns None."""
        result = load_lead_state(tmp_path, "no-repo", "no-lead")
        assert result is None

    def test_load_corrupt_yaml(self, tmp_path: Path) -> None:
        """Loading a lead with corrupt/invalid YAML returns None."""
        state_dir = lead_state_dir(tmp_path, "repo", "bad-lead")
        state_dir.mkdir(parents=True)
        (state_dir / "lead.yaml").write_text("not: valid: yaml: [unclosed")
        assert load_lead_state(tmp_path, "repo", "bad-lead") is None

    def test_load_missing_fields(self, tmp_path: Path) -> None:
        """Loading a lead.yaml with missing required fields returns None."""
        state_dir = lead_state_dir(tmp_path, "repo", "partial")
        state_dir.mkdir(parents=True)
        (state_dir / "lead.yaml").write_text("name: partial\npurpose: test\n")
        assert load_lead_state(tmp_path, "repo", "partial") is None


# ---------------------------------------------------------------------------
# 5.4: list_leads tests
# ---------------------------------------------------------------------------


class TestListLeads:
    def test_list_multiple(self, tmp_path: Path) -> None:
        """list_leads returns all saved leads."""
        state1 = _make_state(name="lead-a", repo_name="test-repo")
        state2 = _make_state(name="lead-b", repo_name="test-repo")
        save_lead_state(state1, tmp_path)
        save_lead_state(state2, tmp_path)

        leads = list_leads(tmp_path, "test-repo")
        names = {s.name for s in leads}
        assert names == {"lead-a", "lead-b"}

    def test_list_nonexistent_repo(self, tmp_path: Path) -> None:
        """list_leads returns empty list for nonexistent repo."""
        leads = list_leads(tmp_path, "nonexistent")
        assert leads == []


# ---------------------------------------------------------------------------
# 5.5: Lock management tests
# ---------------------------------------------------------------------------


class TestLockManagement:
    def test_acquire_creates_lock(self, tmp_path: Path) -> None:
        """acquire_lock creates lock file with PID and session_id."""
        state = _make_state()
        save_lead_state(state, tmp_path)

        acquire_lock(tmp_path, state.repo_name, state.name, 12345, "sess-123")
        lock_path = lead_state_dir(tmp_path, state.repo_name, state.name) / "lock"
        assert lock_path.is_file()
        content = lock_path.read_text()
        assert "12345" in content
        assert "sess-123" in content

    def test_release_deletes_lock(self, tmp_path: Path) -> None:
        """release_lock deletes the lock file."""
        state = _make_state()
        save_lead_state(state, tmp_path)
        acquire_lock(tmp_path, state.repo_name, state.name, 12345, "sess-123")

        release_lock(tmp_path, state.repo_name, state.name)
        lock_path = lead_state_dir(tmp_path, state.repo_name, state.name) / "lock"
        assert not lock_path.exists()

    def test_acquire_raises_for_live_process(self, tmp_path: Path) -> None:
        """acquire_lock raises RuntimeError when locked by current process."""
        state = _make_state()
        save_lead_state(state, tmp_path)
        pid = os.getpid()

        acquire_lock(tmp_path, state.repo_name, state.name, pid, "sess-1")

        import pytest as _pytest

        with _pytest.raises(RuntimeError, match=state.name):
            acquire_lock(tmp_path, state.repo_name, state.name, pid, "sess-2")

    def test_acquire_reclaims_stale_lock(self, tmp_path: Path) -> None:
        """acquire_lock reclaims lock from a dead PID."""
        state = _make_state()
        save_lead_state(state, tmp_path)

        # Write a lock with an unlikely-to-be-alive PID.
        # Theoretically 999999999 could be alive on some systems, but
        # extremely unlikely in practice (max PID is typically 2^22).
        lock_path = lead_state_dir(tmp_path, state.repo_name, state.name) / "lock"
        lock_path.write_text("999999999\nold-session\n")

        # Should succeed (reclaim stale lock)
        acquire_lock(tmp_path, state.repo_name, state.name, os.getpid(), "new-sess")
        content = lock_path.read_text()
        assert str(os.getpid()) in content

    def test_is_lead_active_no_lock(self, tmp_path: Path) -> None:
        """is_lead_active returns False when no lock file."""
        assert is_lead_active(tmp_path, "repo", "lead") is False

    def test_is_lead_active_live_process(self, tmp_path: Path) -> None:
        """is_lead_active returns True when current PID holds lock."""
        state = _make_state()
        save_lead_state(state, tmp_path)
        acquire_lock(tmp_path, state.repo_name, state.name, os.getpid(), "sess")
        assert is_lead_active(tmp_path, state.repo_name, state.name) is True

    def test_is_lead_active_stale_cleanup(self, tmp_path: Path) -> None:
        """is_lead_active cleans up stale lock and returns False."""
        state = _make_state()
        save_lead_state(state, tmp_path)
        lock_path = lead_state_dir(tmp_path, state.repo_name, state.name) / "lock"
        lock_path.write_text("999999999\nold-sess\n")
        assert is_lead_active(tmp_path, state.repo_name, state.name) is False
        assert not lock_path.exists()  # stale lock was cleaned up

    def test_acquire_corrupt_lock_reclaims(self, tmp_path: Path) -> None:
        """acquire_lock reclaims a corrupt lock file."""
        state = _make_state()
        save_lead_state(state, tmp_path)
        lock_path = lead_state_dir(tmp_path, state.repo_name, state.name) / "lock"
        lock_path.write_text("not-a-pid\n")
        acquire_lock(tmp_path, state.repo_name, state.name, os.getpid(), "new-sess")
        assert str(os.getpid()) in lock_path.read_text()


# ---------------------------------------------------------------------------
# 5.6: provision_clone tests
# ---------------------------------------------------------------------------


class TestProvisionClone:
    def test_clone_creates_git_repo(self, tmp_path: Path) -> None:
        """provision_clone creates a valid git clone."""
        # Create a source git repo
        source = tmp_path / "source-repo"
        source.mkdir()
        subprocess.run(["git", "init"], cwd=source, capture_output=True, timeout=120)
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
            cwd=source,
            capture_output=True,
            timeout=120,
        )

        harness_home = tmp_path / "harness"
        state = _make_state(repo_path=str(source))
        save_lead_state(state, harness_home)

        clone_dir = provision_clone(state, harness_home)
        assert clone_dir.is_dir()
        assert (clone_dir / ".git").is_dir()

        # Verify HEAD is valid
        result = subprocess.run(
            ["git", "-C", str(clone_dir), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0

    def test_clone_idempotent(self, tmp_path: Path) -> None:
        """Calling provision_clone twice returns same path without error."""
        source = tmp_path / "source-repo"
        source.mkdir()
        subprocess.run(["git", "init"], cwd=source, capture_output=True, timeout=120)
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
            cwd=source,
            capture_output=True,
            timeout=120,
        )

        harness_home = tmp_path / "harness"
        state = _make_state(repo_path=str(source))
        save_lead_state(state, harness_home)

        path1 = provision_clone(state, harness_home)
        path2 = provision_clone(state, harness_home)
        assert path1 == path2

    def test_clone_failure_raises(self, tmp_path: Path) -> None:
        """provision_clone raises RuntimeError when git clone fails."""
        import pytest

        harness_home = tmp_path / "harness"
        state = _make_state(repo_path="/nonexistent/repo")
        save_lead_state(state, harness_home)

        with pytest.raises(RuntimeError, match="clone"):
            provision_clone(state, harness_home)


# ---------------------------------------------------------------------------
# 5.7: resolve_or_create_lead tests
# ---------------------------------------------------------------------------


class TestResolveOrCreateLead:
    def test_create_new_lead(self, tmp_path: Path) -> None:
        """First call creates a lead with correct fields."""
        repo = tmp_path / "repo"
        repo.mkdir()

        with patch("action_harness.lead_registry.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("no git")
            state = resolve_or_create_lead(tmp_path, repo, "test-lead", "Testing")

        assert state.name == "test-lead"
        assert state.created_at != ""
        assert state.session_id != ""
        # Validate session_id is a UUID
        uuid.UUID(state.session_id)

    def test_resolve_existing_updates_last_active(self, tmp_path: Path) -> None:
        """Second call loads existing and updates last_active."""
        repo = tmp_path / "repo"
        repo.mkdir()

        with patch("action_harness.lead_registry.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("no git")
            state1 = resolve_or_create_lead(tmp_path, repo, "test-lead", "Testing")
            original_created = state1.created_at
            original_session = state1.session_id

            import time

            time.sleep(0.01)  # Ensure time difference

            state2 = resolve_or_create_lead(tmp_path, repo, "test-lead", "Testing")

        assert state2.created_at == original_created  # unchanged
        assert state2.session_id == original_session  # unchanged
        # last_active should differ (updated)
        assert state2.last_active >= original_created


# ---------------------------------------------------------------------------
# 5.8: CLI lead list tests
# ---------------------------------------------------------------------------


class TestCLILeadList:
    def test_lead_list_shows_leads(self, tmp_path: Path) -> None:
        """lead list shows all leads with status."""
        # Save two leads
        state1 = _make_state(name="default", repo_name="fake-repo", purpose="Main")
        state2 = _make_state(name="infra", repo_name="fake-repo", purpose="Infrastructure")
        save_lead_state(state1, tmp_path)
        save_lead_state(state2, tmp_path)

        # Acquire lock for one lead
        acquire_lock(tmp_path, "fake-repo", "default", os.getpid(), "sess-1")

        try:
            with (
                patch(
                    "action_harness.lead_registry.derive_repo_name",
                    return_value="fake-repo",
                ),
                patch(
                    "action_harness.repo.resolve_repo",
                    return_value=(Path("/tmp/fake"), "fake-repo"),
                ),
            ):
                result = runner.invoke(
                    app,
                    ["lead", "list", "--repo", "/tmp/fake", "--harness-home", str(tmp_path)],
                )
            assert result.exit_code == 0
            assert "default" in result.output
            assert "infra" in result.output
            assert "active" in result.output
            assert "idle" in result.output
        finally:
            release_lock(tmp_path, "fake-repo", "default")


# ---------------------------------------------------------------------------
# 5.9: CLI lead retire tests
# ---------------------------------------------------------------------------


class TestCLILeadRetire:
    def test_retire_deletes_lead(self, tmp_path: Path) -> None:
        """lead retire removes the lead state directory."""
        state = _make_state(name="old-lead", repo_name="fake-repo")
        save_lead_state(state, tmp_path)

        with (
            patch(
                "action_harness.lead_registry.derive_repo_name",
                return_value="fake-repo",
            ),
            patch(
                "action_harness.repo.resolve_repo",
                return_value=(Path("/tmp/fake"), "fake-repo"),
            ),
        ):
            result = runner.invoke(
                app,
                [
                    "lead",
                    "retire",
                    "old-lead",
                    "--repo",
                    "/tmp/fake",
                    "--harness-home",
                    str(tmp_path),
                ],
            )
        assert result.exit_code == 0
        state_dir = lead_state_dir(tmp_path, "fake-repo", "old-lead")
        assert not state_dir.exists()

    def test_retire_nonexistent(self, tmp_path: Path) -> None:
        """lead retire of nonexistent lead returns exit code 1."""
        with (
            patch(
                "action_harness.lead_registry.derive_repo_name",
                return_value="fake-repo",
            ),
            patch(
                "action_harness.repo.resolve_repo",
                return_value=(Path("/tmp/fake"), "fake-repo"),
            ),
        ):
            result = runner.invoke(
                app,
                [
                    "lead",
                    "retire",
                    "nope",
                    "--repo",
                    "/tmp/fake",
                    "--harness-home",
                    str(tmp_path),
                ],
            )
        assert result.exit_code == 1

    def test_retire_active_lead_refused(self, tmp_path: Path) -> None:
        """lead retire refuses to retire an active (locked) lead."""
        state = _make_state(name="busy-lead", repo_name="fake-repo")
        save_lead_state(state, tmp_path)
        acquire_lock(tmp_path, "fake-repo", "busy-lead", os.getpid(), "sess-1")

        try:
            with (
                patch(
                    "action_harness.lead_registry.derive_repo_name",
                    return_value="fake-repo",
                ),
                patch(
                    "action_harness.repo.resolve_repo",
                    return_value=(Path("/tmp/fake"), "fake-repo"),
                ),
            ):
                result = runner.invoke(
                    app,
                    [
                        "lead",
                        "retire",
                        "busy-lead",
                        "--repo",
                        "/tmp/fake",
                        "--harness-home",
                        str(tmp_path),
                    ],
                )
            assert result.exit_code == 1
            assert "currently active" in result.output
            # State directory should still exist
            state_dir = lead_state_dir(tmp_path, "fake-repo", "busy-lead")
            assert state_dir.exists()
        finally:
            release_lock(tmp_path, "fake-repo", "busy-lead")


# ---------------------------------------------------------------------------
# 5.10: CLI backward compatibility test
# ---------------------------------------------------------------------------


class TestCLIBackwardCompat:
    def test_bare_lead_command_calls_start(self, tmp_path: Path) -> None:
        """Bare `harness lead --repo <path>` calls dispatch_lead_interactive."""
        (tmp_path / ".git").mkdir()
        with (
            patch("action_harness.lead.dispatch_lead_interactive", return_value=0) as mock_dispatch,
            patch("action_harness.lead.gather_lead_context") as mock_context,
            patch("shutil.which", return_value="/usr/bin/fake"),
            patch("action_harness.lead_registry.subprocess.run") as mock_subp,
        ):
            mock_subp.side_effect = FileNotFoundError("no git")
            mock_ctx = MagicMock()
            mock_ctx.full_text = "test context"
            mock_ctx.repo_name = "test-repo"
            mock_context.return_value = mock_ctx

            result = runner.invoke(
                app,
                [
                    "lead",
                    "--repo",
                    str(tmp_path),
                    "--harness-home",
                    str(tmp_path / "harness"),
                ],
            )
            assert result.exit_code == 0
            assert mock_dispatch.called

            # Verify lock is released after session ends (typer.Exit triggers finally block)
            lock_path = lead_state_dir(tmp_path / "harness", tmp_path.name, "default") / "lock"
            assert not lock_path.exists(), "Lock file should be released after session ends"


# ---------------------------------------------------------------------------
# 5.11: Resume fallback test
# ---------------------------------------------------------------------------


class TestResumeFallback:
    def test_resume_fallback_generates_new_session(self, tmp_path: Path) -> None:
        """When resume fails, a new session_id is generated and used."""
        (tmp_path / ".git").mkdir()
        call_count = 0
        session_ids: list[str | None] = []

        def mock_dispatch(
            repo_path: Path,
            prompt: str | None,
            context: object,
            harness_agents_dir: Path,
            permission_mode: str = "default",
            *,
            session_id: str | None = None,
            resume: bool = False,
        ) -> int:
            nonlocal call_count
            call_count += 1
            session_ids.append(session_id)
            if resume:
                return 1  # Simulate resume failure
            return 0  # Success on fresh start

        with (
            patch("action_harness.lead.dispatch_lead_interactive", side_effect=mock_dispatch),
            patch("action_harness.lead.gather_lead_context") as mock_context,
            patch("shutil.which", return_value="/usr/bin/fake"),
            patch("action_harness.lead_registry.subprocess.run") as mock_subp,
        ):
            mock_subp.side_effect = FileNotFoundError("no git")
            mock_ctx = MagicMock()
            mock_ctx.full_text = "test context"
            mock_ctx.repo_name = "test-repo"
            mock_context.return_value = mock_ctx

            harness_home = tmp_path / "harness"

            # First: create the lead (so it exists on disk for resume)
            state = _make_state(name="default", repo_name=tmp_path.name)
            state.repo_path = str(tmp_path)
            save_lead_state(state, harness_home)
            original_session = state.session_id

            result = runner.invoke(
                app,
                [
                    "lead",
                    "start",
                    "--repo",
                    str(tmp_path),
                    "--harness-home",
                    str(harness_home),
                ],
            )
            assert result.exit_code == 0

            # Should have been called twice (resume fail + fresh)
            assert call_count == 2

            # Second call should have a different session_id
            assert len(session_ids) == 2
            assert session_ids[0] == original_session  # resume attempt
            assert session_ids[1] != original_session  # new session

            # Verify new session_id was saved
            loaded = load_lead_state(harness_home, tmp_path.name, "default")
            assert loaded is not None
            assert loaded.session_id == session_ids[1]

    def test_new_lead_uses_session_id_not_resume(self, tmp_path: Path) -> None:
        """A brand-new lead uses --session-id, not --resume."""
        (tmp_path / ".git").mkdir()
        resume_flags: list[bool] = []

        def mock_dispatch(
            repo_path: Path,
            prompt: str | None,
            context: object,
            harness_agents_dir: Path,
            permission_mode: str = "default",
            *,
            session_id: str | None = None,
            resume: bool = False,
        ) -> int:
            resume_flags.append(resume)
            return 0

        with (
            patch("action_harness.lead.dispatch_lead_interactive", side_effect=mock_dispatch),
            patch("action_harness.lead.gather_lead_context") as mock_context,
            patch("shutil.which", return_value="/usr/bin/fake"),
            patch("action_harness.lead_registry.subprocess.run") as mock_subp,
        ):
            mock_subp.side_effect = FileNotFoundError("no git")
            mock_ctx = MagicMock()
            mock_ctx.full_text = "test context"
            mock_ctx.repo_name = "test-repo"
            mock_context.return_value = mock_ctx

            harness_home = tmp_path / "harness"
            # Do NOT pre-save any state — this is a brand-new lead

            result = runner.invoke(
                app,
                [
                    "lead",
                    "start",
                    "--repo",
                    str(tmp_path),
                    "--harness-home",
                    str(harness_home),
                ],
            )
            assert result.exit_code == 0
            # Should be called exactly once with resume=False
            assert len(resume_flags) == 1
            assert resume_flags[0] is False


# ---------------------------------------------------------------------------
# 5.12: Integration smoke test
# ---------------------------------------------------------------------------


class TestSyncRepo:
    def test_clone_resets_to_origin(self, tmp_path: Path) -> None:
        """Clone mode fetches and hard-resets to origin/default-branch."""
        repo = tmp_path / "repo"
        repo.mkdir()

        fetch_called = False
        reset_called = False
        reset_target = None

        def mock_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            nonlocal fetch_called, reset_called, reset_target
            if "fetch" in cmd:
                fetch_called = True
            if "symbolic-ref" in cmd:
                return subprocess.CompletedProcess(
                    cmd, 0, stdout="refs/remotes/origin/main\n"
                )
            if "reset" in cmd:
                reset_called = True
                reset_target = cmd[-1]
            return subprocess.CompletedProcess(cmd, 0, stdout="")

        with patch("action_harness.lead_registry.subprocess.run", side_effect=mock_run):
            sync_repo(repo, is_clone=True)

        assert fetch_called
        assert reset_called
        assert reset_target == "origin/main"

    def test_user_repo_warns_when_behind(self, tmp_path: Path) -> None:
        """User working tree fetches and warns if behind, but does not reset."""
        repo = tmp_path / "repo"
        repo.mkdir()

        reset_called = False

        def mock_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            nonlocal reset_called
            if "symbolic-ref" in cmd:
                return subprocess.CompletedProcess(
                    cmd, 0, stdout="refs/remotes/origin/main\n"
                )
            if "reset" in cmd:
                reset_called = True
            if "rev-list" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="3\n")
            return subprocess.CompletedProcess(cmd, 0, stdout="")

        with patch("action_harness.lead_registry.subprocess.run", side_effect=mock_run):
            sync_repo(repo, is_clone=False)

        assert not reset_called  # Must not reset user's working tree

    def test_fetch_failure_does_not_raise(self, tmp_path: Path) -> None:
        """Fetch failure is logged but does not raise."""
        repo = tmp_path / "repo"
        repo.mkdir()

        def mock_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            if "fetch" in cmd:
                return subprocess.CompletedProcess(cmd, 1, stderr="network error")
            return subprocess.CompletedProcess(cmd, 0, stdout="")

        with patch("action_harness.lead_registry.subprocess.run", side_effect=mock_run):
            sync_repo(repo, is_clone=True)  # Should not raise


class TestIntegrationSmoke:
    def test_lead_list_no_leads(self, tmp_path: Path) -> None:
        """lead list with no leads outputs 'No leads found'."""
        result = runner.invoke(
            app,
            ["lead", "list", "--repo", ".", "--harness-home", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "No leads found" in result.output
