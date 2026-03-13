## ADDED Requirements

### Requirement: Validate task completion
The OpenSpec review agent SHALL read `tasks.md` for the change and verify all tasks are marked complete (`[x]`). If incomplete tasks remain, the agent SHALL report them as findings and not proceed to archival.

#### Scenario: All tasks complete
- **WHEN** the agent reviews a change where all tasks in `tasks.md` are `[x]`
- **THEN** the agent reports task validation as passed

#### Scenario: Incomplete tasks found
- **WHEN** the agent reviews a change with 2 of 5 tasks still `[ ]`
- **THEN** the agent reports the incomplete tasks as findings and does not archive

#### Scenario: No tasks.md found
- **WHEN** the agent reviews a change that has no `tasks.md` file
- **THEN** the agent reports an error finding that tasks.md is missing and does not archive

### Requirement: Validate delta spec structure
The OpenSpec review agent SHALL run `openspec validate <change-name>` and check the result. If validation fails, the agent SHALL report the validation errors as findings. Structural validation is a hard gate — archival SHALL NOT proceed if validation fails.

#### Scenario: Validation passes
- **WHEN** `openspec validate <change>` returns no errors
- **THEN** the agent reports structural validation as passed

#### Scenario: Validation fails
- **WHEN** `openspec validate <change>` returns errors (e.g., missing scenarios, missing SHALL/MUST)
- **THEN** the agent reports the validation errors as findings and does not archive

### Requirement: Semantic review of spec-implementation alignment
The OpenSpec review agent SHALL read the change's specs and the PR diff, then assess whether the implementation satisfies the spec requirements. Semantic review is advisory — findings are included in the result but do not block archival if structural checks (task completion, validation) pass.

#### Scenario: Implementation matches spec
- **WHEN** the diff includes all capabilities described in the spec
- **THEN** the agent reports semantic review as passed

#### Scenario: Implementation gap found
- **WHEN** the spec requires a `--verbose` flag but the diff does not add one
- **THEN** the agent reports the gap as an advisory finding with the specific requirement that is unmet

### Requirement: Archive completed changes
When structural validations pass (tasks complete, `openspec validate` clean), the OpenSpec review agent SHALL run the archive process for the change. The agent SHALL commit the archive changes (moved files, updated main specs) to the PR branch. Semantic review findings do not block archival.

#### Scenario: Successful archive
- **WHEN** structural validations pass
- **THEN** the agent runs `openspec archive <change> -y`, commits the results, and reports success

#### Scenario: Archive skipped on structural findings
- **WHEN** the agent has structural findings (incomplete tasks or validation errors)
- **THEN** the agent does not archive and returns the findings for review

### Requirement: Push archive changes to PR branch
After archiving, the agent SHALL push the archive commit to the PR branch so the archive changes are part of the same PR as the implementation.

#### Scenario: Archive changes pushed
- **WHEN** the agent archives successfully
- **THEN** the archive commit is pushed to the PR branch and the PR includes both implementation and archive changes

### Requirement: Agent dispatched via Claude Code CLI
The OpenSpec review agent SHALL be dispatched as a Claude Code CLI subprocess in the worktree, consistent with the code worker dispatch pattern. The system prompt SHALL instruct the agent to perform OpenSpec validation, semantic review, and archival. The system prompt SHALL reference `Fission-AI/OpenSpec` on deepwiki for OpenSpec conventions.

#### Scenario: Agent dispatch
- **WHEN** the pipeline reaches the OpenSpec review stage after PR creation
- **THEN** a Claude Code worker is dispatched in the worktree with a system prompt specific to OpenSpec review

### Requirement: Agent outputs structured result
The review agent SHALL output a JSON block as its final message containing: `status` ("approved" or "findings"), `tasks_total`, `tasks_complete`, `validation_passed`, `semantic_review_passed`, `findings` (list of strings), and `archived` (bool). The harness SHALL parse this from the worker output.

#### Scenario: Approved result
- **WHEN** the agent completes with all checks passed and archive done
- **THEN** the output JSON has `status: "approved"` and `archived: true`

#### Scenario: Findings result
- **WHEN** the agent finds incomplete tasks
- **THEN** the output JSON has `status: "findings"`, `archived: false`, and `findings` listing the issues

#### Scenario: Output parse failure
- **WHEN** the review agent's output cannot be parsed as the expected JSON format
- **THEN** the harness returns a findings result with an error indicating parse failure
