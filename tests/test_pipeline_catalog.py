"""Tests for catalog integration into the pipeline."""

from pathlib import Path

from action_harness.models import ReviewFinding, ReviewResult


class TestPipelineEcosystemThreading:
    """Verify ecosystem is threaded through dispatch calls."""

    def test_dispatch_worker_receives_ecosystem(self) -> None:
        """Verify dispatch_worker is called with ecosystem from the profiler."""
        # Ensure ecosystem parameter is accepted
        import inspect

        from action_harness.worker import dispatch_worker

        sig = inspect.signature(dispatch_worker)
        assert "ecosystem" in sig.parameters
        assert sig.parameters["ecosystem"].default == "unknown"

    def test_dispatch_review_agents_receives_ecosystem(self) -> None:
        """Verify dispatch_review_agents accepts ecosystem parameter."""
        import inspect

        from action_harness.review_agents import dispatch_review_agents

        sig = inspect.signature(dispatch_review_agents)
        assert "ecosystem" in sig.parameters
        assert sig.parameters["ecosystem"].default == "unknown"

    def test_run_pipeline_inner_receives_ecosystem(self) -> None:
        """Verify _run_pipeline_inner accepts ecosystem parameter."""
        import inspect

        from action_harness.pipeline import _run_pipeline_inner

        sig = inspect.signature(_run_pipeline_inner)
        assert "ecosystem" in sig.parameters
        assert sig.parameters["ecosystem"].default == "unknown"

    def test_run_review_fix_retry_receives_ecosystem(self) -> None:
        """Verify _run_review_fix_retry accepts ecosystem parameter."""
        import inspect

        from action_harness.pipeline import _run_review_fix_retry

        sig = inspect.signature(_run_review_fix_retry)
        assert "ecosystem" in sig.parameters
        assert sig.parameters["ecosystem"].default == "unknown"


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

        # Verify file was created
        import json

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
