"""Assessment models for codebase readiness scoring."""

from typing import Literal

from pydantic import BaseModel


class Gap(BaseModel):
    """A gap identified in a repository's agentic readiness."""

    severity: Literal["high", "medium", "low"]
    finding: str
    category: str
    proposal_name: str | None = None


class CIMechanicalSignals(BaseModel):
    """Mechanical signals from CI workflow analysis."""

    ci_exists: bool = False
    triggers_on_pr: bool = False
    runs_tests: bool = False
    runs_lint: bool = False
    runs_typecheck: bool = False
    runs_format_check: bool = False
    branch_protection: bool | None = None


class TestabilityMechanicalSignals(BaseModel):
    """Mechanical signals from test structure analysis."""

    test_framework_configured: bool = False
    test_files: int = 0
    test_functions: int = 0
    coverage_configured: bool = False


class ContextMechanicalSignals(BaseModel):
    """Mechanical signals from context file analysis."""

    claude_md: bool = False
    readme: bool = False
    harness_md: bool = False
    agents_md: bool = False
    type_annotations_present: bool = False
    docstrings_present: bool = False


class ToolingMechanicalSignals(BaseModel):
    """Mechanical signals from tooling configuration analysis."""

    package_manager: bool = False
    lockfile_present: bool = False
    lockfile: str | None = None
    mcp_configured: bool = False
    skills_present: bool = False
    docker_configured: bool = False
    cli_tools_available: bool = False


class ObservabilityMechanicalSignals(BaseModel):
    """Mechanical signals from observability analysis."""

    structured_logging_lib: bool = False
    health_endpoint: bool = False
    metrics_lib: bool = False
    tracing_lib: bool = False
    log_level_configurable: bool = False


class IsolationMechanicalSignals(BaseModel):
    """Mechanical signals from isolation analysis."""

    git_repo: bool = False
    lockfile_present: bool = False
    env_example_present: bool = False
    no_committed_secrets: bool = True
    reproducible_build: bool = False


# Union type for all mechanical signal models
MechanicalSignalsUnion = (
    CIMechanicalSignals
    | TestabilityMechanicalSignals
    | ContextMechanicalSignals
    | ToolingMechanicalSignals
    | ObservabilityMechanicalSignals
    | IsolationMechanicalSignals
)


class CategoryScore(BaseModel):
    """Score for a single assessment category."""

    score: int
    mechanical_signals: MechanicalSignalsUnion
    agent_assessment: str | None = None
    gaps: list[Gap] = []


class AssessmentReport(BaseModel):
    """Complete assessment report for a repository."""

    overall_score: int
    categories: dict[str, CategoryScore]
    proposals: list[Gap]
    repo_path: str
    timestamp: str
    mode: Literal["base", "deep", "propose"]
