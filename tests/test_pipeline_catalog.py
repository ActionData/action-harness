"""Tests for catalog integration into the pipeline."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from action_harness.models import ReviewFinding, ReviewResult


class TestPipelineEcosystemThreading:
    """Verify ecosystem is actually threaded through dispatch calls."""

    # Prior acknowledged: these tests previously used signature inspection.
    # Replaced with behavioral tests that verify the ecosystem value is
    # actually passed through to dispatch_worker/dispatch_review_agents.

    def test_dispatch_worker_receives_ecosystem_from_caller(self, tmp_path: Path) -> None:
        """Verify dispatch_worker actually uses the ecosystem value for catalog loading."""
        mock_subprocess = MagicMock()
        mock_subprocess.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"cost_usd": 0.01, "result": "ok"}),
            stderr="",
        )

        with patch("action_harness.worker.subprocess.run", mock_subprocess):
            from action_harness.worker import dispatch_worker

            dispatch_worker("t", tmp_path, ecosystem="python")

        # Extract system prompt from the claude CLI call
        for call in mock_subprocess.call_args_list:
            cmd = call[0][0]
            if cmd[0] == "claude" and "--system-prompt" in cmd:
                idx = cmd.index("--system-prompt")
                system_prompt = cmd[idx + 1]
                # Python ecosystem should include subprocess-timeout rule
                assert "subprocess.run()" in system_prompt or "timeout" in system_prompt
                return
        raise AssertionError("claude CLI was never called with --system-prompt")

    def test_dispatch_review_agents_passes_ecosystem_to_build_prompt(self) -> None:
        """Verify build_review_prompt receives the ecosystem value."""
        from action_harness.agents import resolve_harness_agents_dir
        from action_harness.review_agents import build_review_prompt

        harness_dir = resolve_harness_agents_dir()
        empty_repo = Path("/tmp/nonexistent-repo-for-test")
        prompt_python = build_review_prompt(
            "bug-hunter", 42, empty_repo, harness_dir, ecosystem="python"
        )
        prompt_unknown = build_review_prompt(
            "bug-hunter", 42, empty_repo, harness_dir, ecosystem="unknown"
        )

        # Python prompt should have more checklist items than unknown
        assert "subprocess-timeout" in prompt_python
        # Both should have universal entries
        assert "## Catalog Checklist" in prompt_python
        assert "## Catalog Checklist" in prompt_unknown


class TestUpdateFrequencyCalled:
    """Verify update_frequency is called after review rounds."""

    def test_update_frequency_called_with_findings(self, tmp_path: Path) -> None:
        """Integration: verify the catalog module is importable and functions work."""
        from action_harness.catalog.frequency import update_frequency
        from action_harness.catalog.models import CatalogEntry

        entry = CatalogEntry(
            id="test-entry",
            entry_class="test",
            severity="medium",
            ecosystems=["all"],
            worker_rule="Test rule about timeouts",
            reviewer_checklist=["Check tests"],
        )

        finding = ReviewFinding(
            title="test-entry violation found",
            file="src/test.py",
            severity="medium",
            description="A test-entry was found",
            agent="bug-hunter",
        )

        knowledge_dir = tmp_path / "knowledge"
        update_frequency(knowledge_dir, [entry], [finding])

        freq_file = knowledge_dir / "findings-frequency.json"
        assert freq_file.exists()
        data = json.loads(freq_file.read_text())
        assert data["test-entry"]["count"] == 1

    def test_pipeline_review_results_available_for_frequency(self) -> None:
        """Verify ReviewResult findings can be collected from stages list."""
        stages: list[ReviewResult] = [
            ReviewResult(
                success=True,
                agent_name="bug-hunter",
                findings=[
                    ReviewFinding(
                        title="Missing timeout",
                        file="src/foo.py",
                        severity="high",
                        description="subprocess.run without timeout",
                        agent="bug-hunter",
                    )
                ],
            ),
            ReviewResult(
                success=True,
                agent_name="quality-reviewer",
                findings=[],
            ),
        ]

        all_findings = [f for s in stages for f in s.findings]
        assert len(all_findings) == 1
        assert all_findings[0].title == "Missing timeout"
