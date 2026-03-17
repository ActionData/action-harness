# Project Consolidation — Design

## Approach

Documentation-only change. Update existing files to reflect post-bootstrap reality. No new documentation frameworks or tools.

## Documentation hierarchy

Each file has a clear purpose and audience:

| File | Audience | Purpose |
|------|----------|---------|
| `README.md` | New users, GitHub visitors | What it is, how to install, how to run, doc index |
| `PROJECT_VISION.md` | Contributors, architects | Core beliefs, success criteria, what this is NOT |
| `ARCHITECTURE.md` | Developers, agents | Module map, pipeline flow, data models, design decisions |
| `CLAUDE.md` | Claude Code (interactive) | Build commands, code quality rules, development conventions |
| `HARNESS.md` | Autonomous workers | Eval commands, skill invocations, worker-specific guidance |

## Changes

1. **ARCHITECTURE.md** — Update module map to include all 32 modules. Group by functional area (core pipeline, worker/eval, git/repo, PR/review, advanced features, knowledge catalog, utilities).

2. **README.md** — Update "How it works" to reflect the full pipeline (8 stages, not 6). Add review agents, protected paths, checkpoint resume. Keep it concise.

3. **Orphaned proposal** — Move `openspec/changes/proposal.md` to `openspec/changes/archive/project-proposal.md` as historical reference.

4. **Agent definitions** — Add a section to CLAUDE.md explaining `.harness/agents/` vs `.claude/agents/` purposes.

5. **Docs index** — Add `docs/README.md` indexing research and exploration content.

## Out of scope

- Code changes
- Consolidating or merging documentation files (each has distinct purpose)
- Rewriting PROJECT_VISION.md content
- Changes to HARNESS.md (it's already focused and correct)
