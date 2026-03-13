## ADDED Requirements

### Requirement: CLI accepts model flag
The CLI SHALL accept a `--model` flag that specifies the Claude model to use. When provided, the flag SHALL be passed to the `claude` CLI as `--model <value>`. When omitted, the `--model` flag SHALL NOT be included in the `claude` command. The value is pass-through — the `claude` CLI validates model names, not the harness.

#### Scenario: Model specified
- **WHEN** the operator runs `action-harness run --model opus --change foo --repo .`
- **THEN** the `claude` CLI is invoked with `--model opus`

#### Scenario: Model omitted
- **WHEN** the operator runs without `--model`
- **THEN** the `claude` CLI is invoked without a `--model` flag

### Requirement: CLI accepts effort flag
The CLI SHALL accept an `--effort` flag with values `low`, `medium`, `high`, or `max`. When provided, the flag SHALL be passed to the `claude` CLI. When omitted, the `--effort` flag SHALL NOT be included in the `claude` command. Invalid values SHALL be rejected by the CLI with a non-zero exit code.

#### Scenario: Effort specified
- **WHEN** the operator runs with `--effort high`
- **THEN** the `claude` CLI is invoked with `--effort high`

#### Scenario: Effort omitted
- **WHEN** the operator runs without `--effort`
- **THEN** the `claude` CLI is invoked without an `--effort` flag

#### Scenario: Invalid effort value
- **WHEN** the operator runs with `--effort ultra`
- **THEN** the CLI exits with a non-zero code and an error message indicating valid choices

### Requirement: CLI accepts budget flag
The CLI SHALL accept a `--max-budget-usd` flag that sets a spending cap per worker dispatch. When provided, the flag SHALL be passed to the `claude` CLI. When omitted, the `--max-budget-usd` flag SHALL NOT be included in the `claude` command.

#### Scenario: Budget specified
- **WHEN** the operator runs with `--max-budget-usd 5.00`
- **THEN** the `claude` CLI is invoked with `--max-budget-usd 5.00`

#### Scenario: Budget omitted
- **WHEN** the operator runs without `--max-budget-usd`
- **THEN** the `claude` CLI is invoked without a `--max-budget-usd` flag

### Requirement: CLI accepts permission mode flag
The CLI SHALL accept a `--permission-mode` flag. The default SHALL be `bypassPermissions` for headless operation. The flag SHALL always be passed to the `claude` CLI (it always has a value).

#### Scenario: Default permission mode
- **WHEN** the operator runs without `--permission-mode`
- **THEN** the `claude` CLI is invoked with `--permission-mode bypassPermissions`

#### Scenario: Custom permission mode
- **WHEN** the operator runs with `--permission-mode plan`
- **THEN** the `claude` CLI is invoked with `--permission-mode plan`

### Requirement: Dry-run shows configured values
The `--dry-run` output SHALL include all worker configuration values so the operator can verify before executing. All four config lines SHALL always be shown (using "default" or "none" for unset values).

#### Scenario: Dry-run with custom config
- **WHEN** the operator runs `--dry-run --model sonnet --effort high --max-budget-usd 2.0`
- **THEN** the dry-run output contains `model: sonnet`, `effort: high`, `max-budget-usd: 2.0`, and `permission-mode: bypassPermissions`

#### Scenario: Dry-run with defaults
- **WHEN** the operator runs `--dry-run` without model, effort, or budget flags
- **THEN** the dry-run output contains `model: default`, `effort: default`, `max-budget-usd: none`, and `permission-mode: bypassPermissions`
