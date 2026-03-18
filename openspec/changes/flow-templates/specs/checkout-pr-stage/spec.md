## ADDED Requirements

### Requirement: CheckoutPrStage creates worktree from existing PR
The `CheckoutPrStage` SHALL accept a PR URL or number via stage config, fetch the PR's head branch, and create a git worktree for it. It sets `context.worktree_path`, `context.branch`, and `context.pr_url`.

#### Scenario: Checkout by PR number
- **WHEN** CheckoutPrStage runs with `config: {pr: 42}`
- **THEN** it resolves PR #42's head branch via `gh pr view`, creates a worktree, and sets context fields

#### Scenario: Checkout by PR URL
- **WHEN** CheckoutPrStage runs with `config: {pr: "https://github.com/org/repo/pull/42"}`
- **THEN** it resolves the PR's head branch and creates a worktree

#### Scenario: PR not found
- **WHEN** the specified PR does not exist
- **THEN** the stage returns `success=False` with the error from `gh pr view`

### Requirement: CheckoutPrStage registered as checkout-pr
The stage SHALL be registered in the stage registry as `"checkout-pr"` and available for use in flow templates.

#### Scenario: Used in review-only flow
- **WHEN** a flow template references `stage: checkout-pr`
- **THEN** the stage registry resolves it to `CheckoutPrStage`
