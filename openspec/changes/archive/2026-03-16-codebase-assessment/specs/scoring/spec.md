## ADDED Requirements

### Requirement: Per-category scoring from mechanical signals
Each category score SHALL be computed as a weighted sum of its mechanical sub-signals. Each sub-signal contributes a fixed number of points when present/true. The category score is the sum of points earned, capped at 100.

The scoring weights per category SHALL be:

**ci_guardrails (100 points total):**
| Signal | Points |
|--------|--------|
| `ci_exists` | 15 |
| `triggers_on_pr` | 20 |
| `runs_tests` | 25 |
| `runs_lint` | 15 |
| `runs_typecheck` | 10 |
| `runs_format_check` | 5 |
| `branch_protection` | 10 |

**testability (100 points total):**
| Signal | Points |
|--------|--------|
| `test_framework_configured` | 20 |
| `test_files >= 1` | 15 |
| `test_files >= 5` | 10 |
| `test_functions >= 10` | 15 |
| `test_functions >= 30` | 10 |
| `coverage_configured` | 15 |
| `tests_in_ci` (from ci_guardrails) | 15 |

**context (100 points total):**
| Signal | Points |
|--------|--------|
| `claude_md` | 30 |
| `readme` | 20 |
| `harness_md` | 15 |
| `agents_md` | 10 |
| `type_annotations_present` | 15 |
| `docstrings_present` | 10 |

**tooling (100 points total):**
| Signal | Points |
|--------|--------|
| `package_manager` | 20 |
| `lockfile_present` | 20 |
| `mcp_configured` | 15 |
| `skills_present` | 15 |
| `docker_configured` | 15 |
| `cli_tools_available` | 15 |

**observability (100 points total):**
| Signal | Points |
|--------|--------|
| `structured_logging_lib` | 30 |
| `health_endpoint` | 20 |
| `metrics_lib` | 20 |
| `tracing_lib` | 15 |
| `log_level_configurable` | 15 |

**isolation (100 points total):**
| Signal | Points |
|--------|--------|
| `git_repo` | 15 |
| `lockfile_present` | 20 |
| `env_example_present` | 20 |
| `no_committed_secrets` | 25 |
| `reproducible_build` | 20 |

#### Scenario: CI with full checks scores 100
- **WHEN** all CI signals are true (ci_exists, triggers_on_pr, runs_tests, runs_lint, runs_typecheck, runs_format_check, branch_protection)
- **THEN** the ci_guardrails score SHALL be 100

#### Scenario: CI with only tests scores 60
- **WHEN** ci_exists is true, triggers_on_pr is true, runs_tests is true, all other CI signals are false
- **THEN** the ci_guardrails score SHALL be 60

#### Scenario: No CI scores 0
- **WHEN** ci_exists is false
- **THEN** the ci_guardrails score SHALL be 0

#### Scenario: Empty repo scores 0 across all categories
- **WHEN** all mechanical signals are false/absent
- **THEN** all category scores SHALL be 0

#### Scenario: Partial testability
- **WHEN** test_framework_configured is true, test_files is 3, test_functions is 15, coverage_configured is false, tests_in_ci is true
- **THEN** the testability score SHALL be 75 (20 + 15 + 0 + 15 + 10 + 0 + 15)

### Requirement: Gap identification from low scores
The scoring logic SHALL identify gaps for each category. A gap is any sub-signal that is false/absent and worth >= 15 points. Gaps SHALL be classified by severity based on their point value.

| Points | Severity |
|--------|----------|
| >= 25 | high |
| >= 15 | medium |
| < 15 | low |

#### Scenario: Missing tests in CI is a medium gap
- **WHEN** `runs_tests` is false (25 points)
- **THEN** a gap SHALL be identified with severity `high`, category `ci_guardrails`, and `proposal_name` `add-ci-tests`

#### Scenario: Missing CLAUDE.md is a high gap
- **WHEN** `claude_md` is false (30 points)
- **THEN** a gap SHALL be identified with severity `high`, category `context`, and `proposal_name` `add-claude-md`

#### Scenario: Missing format check is not a gap
- **WHEN** `runs_format_check` is false (5 points)
- **THEN** no gap SHALL be identified for this signal (below 15-point threshold)

### Requirement: Agent assessment adjusts scores within bounds
When `--deep` is used, the assessment agent MAY adjust category scores up or down by at most 20 points from the mechanical score. The agent SHALL provide rationale for any adjustment.

#### Scenario: Agent raises testability score
- **WHEN** the mechanical testability score is 60 and the agent determines tests are high quality despite low count
- **THEN** the agent MAY adjust the score up to 80 (max +20)

#### Scenario: Agent lowers CI score
- **WHEN** the mechanical CI score is 90 but the agent determines the test step only runs `echo "tests pass"`
- **THEN** the agent MAY adjust the score down to 70 (max -20)

#### Scenario: Agent adjustment exceeds bounds
- **WHEN** the agent attempts to adjust a score by more than 20 points
- **THEN** the harness SHALL clamp the adjustment to ±20
