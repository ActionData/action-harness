## Context

OpenSpec changes live at `openspec/changes/<name>/` with a `.openspec.yaml` config file. Completed changes are archived to `openspec/changes/archive/<date>-<name>/`. The harness needs to know which active changes can be implemented without waiting for other changes to land first.

## Goals / Non-Goals

**Goals:**
- `prerequisites` field in `.openspec.yaml` (list of change names)
- Build dependency graph from all active changes
- `harness ready --repo <path>` lists changes with all prerequisites satisfied
- `--json` for machine-readable output
- Integration with lead context gathering

**Non-Goals:**
- Enforcing prerequisites at pipeline start (advisory, not blocking)
- Cross-repo prerequisites
- Circular dependency detection beyond simple validation

## Decisions

### 1. Prerequisites in .openspec.yaml

```yaml
# openspec/changes/merge-queue/.openspec.yaml
schema: spec-driven
prerequisites:
  - repo-lead
  - always-on
```

The field is optional. Changes without `prerequisites` have no dependencies and are always ready.

### 2. Readiness check

A change is "ready" when:
- It has an active change directory (`openspec/changes/<name>/`)
- All names in its `prerequisites` list are either: (a) archived (`openspec/changes/archive/*-<name>/` exists), or (b) have a main spec (`openspec/specs/<name>/spec.md` exists — indicating the change was completed and archived)
- It is not itself completed

### 3. `harness ready` output

```
Ready to implement:
  openspec-prerequisites  (0 prerequisites)
  failure-reporting       (1/1 prerequisites met: agent-knowledge-catalog ✓)

Blocked:
  merge-queue             (0/2: repo-lead ✗, always-on ✗)
  always-on               (0/1: repo-lead ✗)
```

### 4. Lead integration

`gather_lead_context` includes a "Ready Changes" section listing changes from `harness ready --json`. The lead uses this to recommend which changes to dispatch.

## Risks / Trade-offs

- [Stale prerequisites] Prerequisites reference change names that may be renamed → Mitigation: validation warns about unknown prerequisite names.
- [OpenSpec CLI compatibility] Adding fields to `.openspec.yaml` might conflict with OpenSpec CLI → Mitigation: the field is harness-specific. OpenSpec CLI ignores unknown fields.
