"""Tests for skill discovery and injection."""

from pathlib import Path

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
    def test_returns_valid_path(self) -> None:
        """resolve_harness_skills_dir returns a path to .claude/skills/."""
        result = resolve_harness_skills_dir()
        # In source checkout, this should find the repo's .claude/skills/
        assert result.name == "skills"
        assert result.parent.name == ".claude"


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
