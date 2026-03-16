"""Tests for agent definition file loading."""

import textwrap
from pathlib import Path

import pytest

from action_harness.agents import load_agent_prompt, parse_agent_file


class TestParseAgentFile:
    def test_with_frontmatter(self, tmp_path: Path) -> None:
        """6.1: Parse agent file with valid frontmatter."""
        agent_file = tmp_path / "test-agent.md"
        agent_file.write_text("---\nname: test\n---\nPrompt body")

        meta, body = parse_agent_file(agent_file)

        assert meta == {"name": "test"}
        assert body == "Prompt body"

    def test_without_frontmatter(self, tmp_path: Path) -> None:
        """6.2: Parse agent file without frontmatter."""
        agent_file = tmp_path / "test-agent.md"
        agent_file.write_text("Prompt body")

        meta, body = parse_agent_file(agent_file)

        assert meta == {}
        assert body == "Prompt body"

    def test_with_malformed_yaml(self, tmp_path: Path) -> None:
        """6.3: Parse agent file with malformed YAML frontmatter."""
        agent_file = tmp_path / "test-agent.md"
        agent_file.write_text("---\n: invalid: yaml:\n---\nBody")

        meta, body = parse_agent_file(agent_file)

        assert meta == {}
        assert "Body" in body

    def test_frontmatter_with_multiple_fields(self, tmp_path: Path) -> None:
        """Frontmatter with name and description."""
        agent_file = tmp_path / "agent.md"
        agent_file.write_text(
            textwrap.dedent("""\
                ---
                name: bug-hunter
                description: Finds bugs
                ---
                You are a bug finder.""")
        )

        meta, body = parse_agent_file(agent_file)

        assert meta == {"name": "bug-hunter", "description": "Finds bugs"}
        assert body == "You are a bug finder."


class TestLoadAgentPrompt:
    def test_repo_override(self, tmp_path: Path) -> None:
        """6.4: Repo override takes precedence over harness default."""
        repo_path = tmp_path / "repo"
        repo_agents = repo_path / ".harness" / "agents"
        repo_agents.mkdir(parents=True)
        (repo_agents / "bug-hunter.md").write_text("---\nname: bug-hunter\n---\nrepo version")

        harness_dir = tmp_path / "harness"
        harness_dir.mkdir()
        (harness_dir / "bug-hunter.md").write_text("---\nname: bug-hunter\n---\ndefault version")

        result = load_agent_prompt("bug-hunter", repo_path, harness_dir)
        assert result == "repo version"

    def test_fallback_to_harness_default(self, tmp_path: Path) -> None:
        """6.5: Falls back to harness default when no repo override exists."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        harness_dir = tmp_path / "harness"
        harness_dir.mkdir()
        (harness_dir / "bug-hunter.md").write_text("---\nname: bug-hunter\n---\ndefault version")

        result = load_agent_prompt("bug-hunter", repo_path, harness_dir)
        assert result == "default version"

    def test_missing_agent_raises(self, tmp_path: Path) -> None:
        """6.6: FileNotFoundError raised when agent not found in either location."""
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        harness_dir = tmp_path / "harness"
        harness_dir.mkdir()

        with pytest.raises(FileNotFoundError, match="nonexistent-agent"):
            load_agent_prompt("nonexistent-agent", repo_path, harness_dir)


class TestDefaultAgentFiles:
    def test_all_default_agents_exist_and_have_frontmatter(self) -> None:
        """6.9: Verify all 5 default agent files exist with valid frontmatter."""
        agents_dir = Path(__file__).resolve().parent.parent / ".harness" / "agents"
        expected_agents = [
            "bug-hunter.md",
            "test-reviewer.md",
            "quality-reviewer.md",
            "spec-compliance-reviewer.md",
            "openspec-reviewer.md",
        ]

        for agent_file_name in expected_agents:
            agent_path = agents_dir / agent_file_name
            assert agent_path.exists(), f"Missing agent file: {agent_file_name}"

            meta, body = parse_agent_file(agent_path)
            assert "name" in meta, f"Missing 'name' in frontmatter of {agent_file_name}"
            assert (
                "description" in meta
            ), f"Missing 'description' in frontmatter of {agent_file_name}"
            assert len(body) > 0, f"Empty body in {agent_file_name}"
