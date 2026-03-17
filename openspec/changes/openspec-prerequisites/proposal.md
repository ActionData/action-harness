## Why

The roadmap describes change ordering in prose, but there's no machine-readable way to determine which changes are ready to implement. The repo-lead and harness need to answer "what's ready to work on?" — which requires knowing prerequisites. Today, a human reads the roadmap and manually determines ordering.

Machine-readable prerequisites in each change's `.openspec.yaml` would let the harness compute unblocked changes, validate ordering, and let the repo-lead make informed dispatch decisions.

## What Changes

- Add optional `prerequisites` field to `.openspec.yaml` for each change (list of change names)
- New CLI command: `harness ready --repo <path>` that reads all changes, builds a dependency graph, and lists unblocked changes (those with all prerequisites completed/archived)
- Integration with `harness lead`: the lead's context includes which changes are ready to dispatch

## Capabilities

### New Capabilities
- `openspec-prerequisites`: Machine-readable prerequisites in `.openspec.yaml`, dependency graph computation, `harness ready` command.

### Modified Capabilities
None

## Impact

- `.openspec.yaml` files — optional `prerequisites` field added
- `cli.py` — new `ready` command
- New module `src/action_harness/prerequisites.py` — YAML parsing, graph computation, readiness check
- `lead.py` — context gathering includes ready changes
