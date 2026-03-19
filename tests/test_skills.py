"""Tests for skill discovery and injection."""

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import action_harness.skills as skills_mod
from action_harness.skills import (
    INJECTED_MARKER,
    SKILL_FILENAME,
    discover_skills,
    inject_skills,
    resolve_harness_skills_dir,
)


def _make_skill(skills_dir: Path, name: str, content: str = "---\nname: test\n---\nBody") -> Path:
    """Create a skill directory with a SKILL.md file."""
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / SKILL_FILENAME).write_text(content)
    return skill_dir


class TestResolveHarnessSkillsDir:
    def test_returns_valid_path_with_skills(self) -> None:
        """resolve_harness_skills_dir returns a path that exists and contains skills."""
        result = resolve_harness_skills_dir()
        assert result.name == "skills"
        # Plugin root: skills/ sits alongside .claude-plugin/ at the repo root
        plugin_json = result.parent / ".claude-plugin" / "plugin.json"
        assert plugin_json.is_file(), "skills/ should be in the plugin root"
        # Verify we got the source-checkout path (not the fallback)
        assert result.is_dir(), "resolved skills dir should exist"
        # Should contain at least one skill subdirectory with SKILL.md
        skill_dirs = [d for d in result.iterdir() if d.is_dir() and (d / SKILL_FILENAME).is_file()]
        assert len(skill_dirs) > 0, "skills dir should contain at least one skill"

    def test_fallback_when_source_tree_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Falls back to importlib.resources when no source checkout found."""
        fake_file = tmp_path / "src" / "action_harness" / "skills.py"
        fake_file.parent.mkdir(parents=True)
        fake_file.write_text("")
        monkeypatch.setattr(skills_mod, "__file__", str(fake_file))

        result = resolve_harness_skills_dir()
        # Should fall through to importlib.resources fallback
        assert "default_skills" in str(result)


class TestDiscoverSkills:
    def test_finds_skill_directories(self, tmp_path: Path) -> None:
        """discover_skills finds directories containing SKILL.md."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _make_skill(skills_dir, "skill-a")
        _make_skill(skills_dir, "skill-b")

        result = discover_skills(skills_dir)

        assert result == ["skill-a", "skill-b"]

    def test_ignores_dirs_without_skill_md(self, tmp_path: Path) -> None:
        """discover_skills ignores directories that don't have SKILL.md."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _make_skill(skills_dir, "valid-skill")

        # Create a directory without SKILL.md
        no_skill = skills_dir / "not-a-skill"
        no_skill.mkdir()
        (no_skill / "README.md").write_text("not a skill")

        result = discover_skills(skills_dir)

        assert result == ["valid-skill"]

    def test_returns_sorted(self, tmp_path: Path) -> None:
        """discover_skills returns skills in sorted order."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _make_skill(skills_dir, "zebra-skill")
        _make_skill(skills_dir, "alpha-skill")
        _make_skill(skills_dir, "mid-skill")

        result = discover_skills(skills_dir)

        assert result == ["alpha-skill", "mid-skill", "zebra-skill"]

    def test_missing_dir_returns_empty(self, tmp_path: Path) -> None:
        """discover_skills returns empty list for nonexistent directory."""
        result = discover_skills(tmp_path / "nonexistent")

        assert result == []

    def test_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        """discover_skills returns empty list for empty directory."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        result = discover_skills(skills_dir)

        assert result == []


class TestInjectSkills:
    def test_copies_skills_into_target(self, tmp_path: Path) -> None:
        """inject_skills copies skill directories into target worktree."""
        source = tmp_path / "source" / "skills"
        source.mkdir(parents=True)
        _make_skill(source, "my-skill")

        worktree = tmp_path / "worktree"
        worktree.mkdir()

        result = inject_skills(source, worktree)

        assert result == ["my-skill"]
        target_skill = worktree / ".claude" / "skills" / "my-skill" / SKILL_FILENAME
        assert target_skill.exists()
        assert "Body" in target_skill.read_text()

    def test_skips_existing_skills(self, tmp_path: Path) -> None:
        """inject_skills does not overwrite existing target skills."""
        source = tmp_path / "source" / "skills"
        source.mkdir(parents=True)
        _make_skill(source, "existing-skill", content="harness version")

        worktree = tmp_path / "worktree"
        target_skills = worktree / ".claude" / "skills"
        target_skills.mkdir(parents=True)
        _make_skill(target_skills, "existing-skill", content="repo version")

        result = inject_skills(source, worktree)

        assert result == []
        # Verify original content is preserved
        content = (target_skills / "existing-skill" / SKILL_FILENAME).read_text()
        assert content == "repo version"

    def test_writes_harness_injected_marker(self, tmp_path: Path) -> None:
        """inject_skills writes .harness-injected marker listing injected skills."""
        source = tmp_path / "source" / "skills"
        source.mkdir(parents=True)
        _make_skill(source, "skill-a")
        _make_skill(source, "skill-b")

        worktree = tmp_path / "worktree"
        worktree.mkdir()

        inject_skills(source, worktree)

        marker = worktree / ".claude" / "skills" / INJECTED_MARKER
        assert marker.exists()
        content = marker.read_text()
        assert "skill-a" in content
        assert "skill-b" in content

    def test_writes_gitignore_for_injected_skills(self, tmp_path: Path) -> None:
        """inject_skills writes .gitignore to prevent injected skills from being committed."""
        source = tmp_path / "source" / "skills"
        source.mkdir(parents=True)
        _make_skill(source, "skill-a")
        _make_skill(source, "skill-b")

        worktree = tmp_path / "worktree"
        worktree.mkdir()

        inject_skills(source, worktree)

        gitignore = worktree / ".claude" / "skills" / ".gitignore"
        assert gitignore.exists()
        content = gitignore.read_text()
        assert "skill-a/" in content
        assert "skill-b/" in content
        assert INJECTED_MARKER in content

    def test_appends_to_existing_gitignore(self, tmp_path: Path) -> None:
        """inject_skills appends to existing .gitignore without clobbering."""
        source = tmp_path / "source" / "skills"
        source.mkdir(parents=True)
        _make_skill(source, "new-skill")

        worktree = tmp_path / "worktree"
        target_skills = worktree / ".claude" / "skills"
        target_skills.mkdir(parents=True)
        gitignore = target_skills / ".gitignore"
        gitignore.write_text("existing-pattern/\n")

        inject_skills(source, worktree)

        content = gitignore.read_text()
        assert "existing-pattern/" in content
        assert "new-skill/" in content

    def test_no_marker_when_nothing_injected(self, tmp_path: Path) -> None:
        """inject_skills does not write marker when no skills were injected."""
        source = tmp_path / "source" / "skills"
        source.mkdir(parents=True)
        # No skills in source

        worktree = tmp_path / "worktree"
        worktree.mkdir()

        result = inject_skills(source, worktree)

        assert result == []
        marker = worktree / ".claude" / "skills" / INJECTED_MARKER
        assert not marker.exists()

    def test_handles_missing_source_dir(self, tmp_path: Path) -> None:
        """inject_skills returns empty list when source dir doesn't exist."""
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        result = inject_skills(tmp_path / "nonexistent", worktree)

        assert result == []

    def test_mixed_existing_and_new(self, tmp_path: Path) -> None:
        """inject_skills copies new skills and skips existing ones."""
        source = tmp_path / "source" / "skills"
        source.mkdir(parents=True)
        _make_skill(source, "new-skill")
        _make_skill(source, "existing-skill", content="harness version")

        worktree = tmp_path / "worktree"
        target_skills = worktree / ".claude" / "skills"
        target_skills.mkdir(parents=True)
        _make_skill(target_skills, "existing-skill", content="repo version")

        result = inject_skills(source, worktree)

        assert result == ["new-skill"]
        # New skill was copied
        assert (target_skills / "new-skill" / SKILL_FILENAME).exists()
        # Existing skill was not overwritten
        content = (target_skills / "existing-skill" / SKILL_FILENAME).read_text()
        assert content == "repo version"

    def test_creates_target_dir_if_needed(self, tmp_path: Path) -> None:
        """inject_skills creates .claude/skills/ if it doesn't exist."""
        source = tmp_path / "source" / "skills"
        source.mkdir(parents=True)
        _make_skill(source, "my-skill")

        worktree = tmp_path / "worktree"
        worktree.mkdir()
        # .claude/skills/ does not exist yet

        result = inject_skills(source, worktree)

        assert result == ["my-skill"]
        assert (worktree / ".claude" / "skills" / "my-skill").is_dir()

    def test_idempotent_reinjection(self, tmp_path: Path) -> None:
        """inject_skills is idempotent — second call skips already-injected skills."""
        source = tmp_path / "source" / "skills"
        source.mkdir(parents=True)
        _make_skill(source, "skill-a")

        worktree = tmp_path / "worktree"
        worktree.mkdir()

        first = inject_skills(source, worktree)
        assert first == ["skill-a"]

        second = inject_skills(source, worktree)
        assert second == []

        # Marker and gitignore still intact
        marker = worktree / ".claude" / "skills" / INJECTED_MARKER
        assert marker.exists()
        gitignore = worktree / ".claude" / "skills" / ".gitignore"
        assert gitignore.exists()

    def test_partial_copytree_failure(self, tmp_path: Path) -> None:
        """inject_skills continues past a single skill copy failure."""
        source = tmp_path / "source" / "skills"
        source.mkdir(parents=True)
        _make_skill(source, "good-skill")
        _make_skill(source, "bad-skill")

        worktree = tmp_path / "worktree"
        worktree.mkdir()

        original_copytree = shutil.copytree

        def failing_copytree(src: str, dst: str, *args: object, **kwargs: object) -> str:
            if "bad-skill" in src:
                raise OSError("simulated copy failure")
            return original_copytree(src, dst)

        with patch("action_harness.skills.shutil.copytree", side_effect=failing_copytree):
            result = inject_skills(source, worktree)

        # good-skill was injected, bad-skill was not
        assert result == ["good-skill"]
        assert (worktree / ".claude" / "skills" / "good-skill").is_dir()
        assert not (worktree / ".claude" / "skills" / "bad-skill").exists()

    def test_gitignore_no_substring_false_positive(self, tmp_path: Path) -> None:
        """Gitignore dedup uses line matching, not substring matching."""
        source = tmp_path / "source" / "skills"
        source.mkdir(parents=True)
        _make_skill(source, "foo")

        worktree = tmp_path / "worktree"
        target_skills = worktree / ".claude" / "skills"
        target_skills.mkdir(parents=True)
        # Existing gitignore has "foobar/" which should NOT prevent "foo/"
        gitignore = target_skills / ".gitignore"
        gitignore.write_text("foobar/\n")

        inject_skills(source, worktree)

        content = gitignore.read_text()
        lines = content.splitlines()
        assert "foo/" in lines, "foo/ should be added despite foobar/ existing"


class TestPipelineSkillInjection:
    """Verify inject_skills is called during pipeline execution."""

    def test_inject_skills_called_after_worktree_before_dispatch(self, tmp_path: Path) -> None:
        """Pipeline calls inject_skills after worktree creation, before worker dispatch."""
        from action_harness.pipeline import run_pipeline

        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()

        call_order: list[str] = []
        mock = MagicMock()

        def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            result.stderr = ""
            if cmd[0] == "claude":
                call_order.append("worker_dispatch")
                result.stdout = json.dumps({"cost_usd": 0.01, "result": "ok"})
            elif cmd[0] == "git" and "rev-list" in cmd:
                result.stdout = "1\n"
            elif cmd[0] == "git" and "symbolic-ref" in cmd:
                result.stdout = "refs/remotes/origin/main\n"
            elif cmd[0] == "git" and "worktree" in cmd and "add" in cmd:
                call_order.append("worktree_create")
                result.stdout = ""
            elif cmd[0] == "gh" and "pr" in cmd and "create" in cmd:
                result.stdout = "https://github.com/test/repo/pull/1\n"
            else:
                result.stdout = ""
            return result

        mock.side_effect = side_effect

        def mock_inject_fn(source: Path, worktree: Path, **kwargs: object) -> list[str]:
            call_order.append("skill_injection")
            return ["test-skill"]

        with (
            patch("action_harness.pipeline.subprocess.run", mock),
            patch("action_harness.worker.subprocess.run", mock),
            patch("action_harness.evaluator.subprocess.run", mock),
            patch("action_harness.pr.subprocess.run", mock),
            patch("action_harness.worktree.subprocess.run", mock),
            patch(
                "action_harness.protection.load_protected_patterns",
                return_value=[],
            ),
            patch(
                "action_harness.pipeline.inject_skills",
                side_effect=mock_inject_fn,
            ) as mock_inject,
            patch(
                "action_harness.pipeline.resolve_harness_skills_dir",
            ) as mock_resolve,
        ):
            mock_resolve.return_value = tmp_path / "fake-skills"
            run_pipeline(
                change_name="test-change",
                repo=repo,
                max_retries=0,
                max_turns=10,
                skip_review=True,
                prompt="Test prompt",
            )

        # Verify inject_skills was called
        mock_inject.assert_called_once()
        call_args = mock_inject.call_args
        assert call_args[0][0] == tmp_path / "fake-skills"
        # Second arg is the worktree path — verify it's under the repo
        worktree_arg = call_args[0][1]
        assert isinstance(worktree_arg, Path)
        assert "harness" in str(worktree_arg) or "test-change" in str(worktree_arg)

        # Verify ordering: worktree created before skills injected,
        # skills injected before worker dispatched
        wt_idx = call_order.index("worktree_create")
        sk_idx = call_order.index("skill_injection")
        wd_idx = call_order.index("worker_dispatch")
        assert wt_idx < sk_idx < wd_idx, (
            f"Expected worktree < injection < dispatch, got: {call_order}"
        )
