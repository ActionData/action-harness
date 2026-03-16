# Agent Quality Catalog — Research Notes

Date: 2026-03-16

## Origin

After running the harness on 5 roadmap items (auto-merge, harness-md, unspecced-tasks, github-issue-intake, codebase-assessment), the review agents consistently found similar classes of bugs across all PRs. We fixed 7 Tier 1 issues and identified 13 Tier 2 issues. The patterns are universal — they apply to any Python codebase, and many are language-agnostic.

This raises the question: how do we prevent these classes of bugs rather than just detecting them after implementation?

## The Problem

The review agents already detect most of these issues. The problem isn't detection — it's that:
1. The implementing agent doesn't know the rules before it writes code
2. After 2 rounds of fix-retry, some findings remain unresolved
3. The same classes of bugs recur across different changes

## Bug/Quality Issue Classes

Derived from actual findings across PRs #31-35:

### Class: Defensive I/O
- **subprocess-timeout**: `subprocess.run()` without `timeout=` can hang indefinitely
- **file-read-safety**: File reads without try/except crash on permission/encoding errors
- **Ecosystems**: Python, Ruby, any language with subprocess calls
- **Severity**: High — hangs block the entire pipeline

### Class: Language Pitfalls
- **bare-assert-narrowing**: `assert x is not None` stripped by `python -O`, leaving type unguarded
- **Ecosystems**: Python
- **Severity**: Medium — silent at runtime until optimized mode is used

### Class: Pattern Safety
- **regex-word-boundary**: Missing `\b` causes false matches (`change:` matches `exchange:`)
- **Ecosystems**: All
- **Severity**: Medium — silent incorrect behavior

### Class: Error Clarity
- **generic-error-messages**: "Not found" instead of the actual error from stderr
- **Ecosystems**: All
- **Severity**: Medium — hinders debugging

### Class: Ordering
- **validate-before-operate**: Calling external tools before checking they exist
- **Ecosystems**: All
- **Severity**: Medium — confusing error messages

### Class: Consistency
- **inconsistent-error-handling**: New function in a module doesn't match existing patterns
- **Ecosystems**: All
- **Severity**: Medium — broken windows, compounds over time

### Class: DRY Violation
- **duplicated-utility**: Copying a function instead of importing from canonical location
- **Ecosystems**: All
- **Severity**: Medium — diverges over time, weaker copy may lack features

### Class: Preview Fidelity
- **dry-run-mismatch**: `--dry-run` output doesn't match actual pipeline behavior
- **Ecosystems**: All (CLI tools)
- **Severity**: Medium — misleading operator preview

### Class: Dead Code
- **dead-gate**: Condition that can never trigger due to earlier control flow
- **Ecosystems**: All
- **Severity**: Low — misleading but not incorrect

### Class: Stringly Typed
- **string-field-access**: Using `getattr(obj, field_name_string)` with no validation
- **Ecosystems**: Python
- **Severity**: Medium — typo silently produces wrong results

## Context Hierarchy

The key insight: different agents need different subsets of this knowledge, delivered through different mechanisms.

```
┌──────────────────────────────────────────────────────────────┐
│  Layer 0: UNIVERSAL (all repos, all ecosystems)              │
│  "Validate before operate"                                   │
│  "Include error context in messages"                         │
│  "Preview output must match actual behavior"                 │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Layer 1: ECOSYSTEM (Python, JS, Rust, Go...)        │   │
│  │  "subprocess.run needs timeout" (Python)             │   │
│  │  "no bare assert narrowing" (Python)                 │   │
│  │  "no unwrap() in prod" (Rust)                        │   │
│  │  "await needs try/catch" (JS)                        │   │
│  │                                                       │   │
│  │  ┌──────────────────────────────────────────┐        │   │
│  │  │  Layer 2: REPO-SPECIFIC (HARNESS.md)     │        │   │
│  │  │  "Use typer.echo for stderr"             │        │   │
│  │  │  "ValidationError for input errors"      │        │   │
│  │  │  "auth module deprecated"                │        │   │
│  │  └──────────────────────────────────────────┘        │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘

Principle: a rule lives at the outermost layer where it's universally true.
Inner layers only contain what's NOT in the layer above.
```

## Delivery Mechanisms

### Worker Agent (implementing)
Gets a lean slice — top rules from layers 0+1, plus all of layer 2 (HARNESS.md).
Context window is the constraint: every KB of rules competes with implementation context.

### Review Agents (bug-hunter, test-reviewer, quality-reviewer)
Get the full catalog across all layers.
Review agents are read-only — they have budget for a rich checklist.
This is where most detection happens.

### Codebase Assessment
Uses the catalog as a scoring rubric.
"Does this repo have subprocess timeouts?" → score impact.
Can propose adding missing patterns via gap proposals.

## Smart Filtering

The catalog should be filtered based on what's already covered:

- Repo has ruff with specific rules enabled → skip rules that ruff catches
- Repo has mypy strict mode → skip type-related rules
- Repo has no subprocess usage → skip subprocess timeout rule
- Repo already has CLAUDE.md with the rule → skip (already in layer 2)

This connects to `codebase-assessment` — the scanner already detects what tools are configured.

## Self-Improving Loop

The catalog can grow from review findings:

```
Agent writes code
  → Review agent finds bug
    → Bug classified against catalog
      → New entry proposed (if novel)
        → Approved by human
          → Future agents avoid this class
            → Quality improves across all repos
```

The `learned_from` field on catalog entries traces each rule back to the specific PR/finding that taught it.

## Catalog Entry Structure (Draft)

```yaml
id: subprocess-timeout
class: defensive-io
severity: high
ecosystems: [python]

worker_rule: >
  Every subprocess.run() call must include a timeout= parameter.

reviewer_checklist:
  - Check all subprocess.run calls have timeout= parameter
  - Check except clauses include subprocess.TimeoutExpired
  - Verify timeout value is reasonable (30-600s)

assessment:
  scan: "subprocess.run calls without timeout="
  score_category: isolation
  points_deduction: 10

examples:
  bad: subprocess.run(cmd, capture_output=True)
  good: subprocess.run(cmd, capture_output=True, timeout=120)

learned_from:
  - pr: "#34"
    finding: "No subprocess timeout on gh CLI calls"
    date: "2026-03-15"
```

## Application to Agent-Unfriendly Repos

For repos that aren't agent-ready, the catalog drives a progressive improvement loop:

1. `harness assess --repo ./path` → scores low on context, testability, etc.
2. `harness assess --propose` → generates proposals to add missing infrastructure
3. Harness implements proposals (CLAUDE.md, tests, CI, lint config)
4. Subsequent runs benefit from improved context
5. Review agents find fewer issues
6. Quality improves organically

The catalog is both the diagnostic criteria (what to check) and the prescription (what to add). This makes the harness more effective on older codebases by systematically filling the gaps.

## Next Steps

This research should inform a roadmap item: `agent-knowledge-catalog`. The implementation would:

1. Define the catalog structure (YAML entries in `src/action_harness/catalog/`)
2. Build a loader that filters by ecosystem
3. Build renderers for worker prompts, reviewer prompts, and assessment scoring
4. Seed with the ~10 entries identified from PRs #31-35
5. Wire into worker dispatch (inject top N rules into system prompt)
6. Wire into review agent dispatch (inject full checklist)
7. Wire into codebase-assessment (use for scoring and gap detection)

## Related

- CLAUDE.md and HARNESS.md now contain the repo-specific rules (Layer 2) from this analysis
- `codebase-assessment` (completed) already has the scanning and scoring infrastructure
- `repo-profiling` (completed) detects ecosystem and tools
- See `docs/research/ephemeral-observability-for-agents.md` for runtime-level quality signals
- See `docs/research/long-running-agent-harness-patterns.md` for session-level quality patterns
