## 1. Plugin Manifest

- [x] 1.1 Create `.claude-plugin/plugin.json` with `{"name": "action", "description": "Action-harness: self-hosting pipeline for Claude Code workers. Provides OpenSpec workflow skills, dispatch skills, and repo assessment tools."}`.

## 2. Migrate Skills

- [x] 2.1 Create `skills/` directory at the repo root.
- [x] 2.2 Move `.claude/skills/openspec-propose/SKILL.md` to `skills/opsx-propose/SKILL.md`. Update the `name` field in frontmatter from `openspec-propose` to `opsx-propose`.
- [x] 2.3 Move `.claude/skills/openspec-apply-change/SKILL.md` to `skills/opsx-apply/SKILL.md`. Update the `name` field from `openspec-apply-change` to `opsx-apply`.
- [x] 2.4 Move `.claude/skills/openspec-review/SKILL.md` to `skills/opsx-review/SKILL.md`. Update the `name` field from `openspec-review` to `opsx-review`.
- [x] 2.5 Move `.claude/skills/openspec-explore/SKILL.md` to `skills/opsx-explore/SKILL.md`. Update the `name` field from `openspec-explore` to `opsx-explore`.
- [x] 2.6 Move `.claude/skills/openspec-archive-change/SKILL.md` to `skills/opsx-archive/SKILL.md`. Update the `name` field from `openspec-archive-change` to `opsx-archive`.
- [x] 2.7 Remove the empty `.claude/skills/` directory after all skills are moved.
- [x] 2.8 Remove `.claude/commands/opsx/` directory (legacy commands superseded by skills).

## 3. Migrate Interactive Agents

- [ ] 3.1 Create `agents/` directory at the repo root (the plugin agents directory).
- [ ] 3.2 Move `.claude/agents/spec-reviewer.md` to `agents/spec-reviewer.md`. Preserve all frontmatter and content.
- [ ] 3.3 Remove the empty `.claude/agents/` directory after migration.

## 4. Update References

- [ ] 4.1 In `CLAUDE.md`, update the "Agent definitions" section to document the new layout: plugin agents in `agents/` (interactive), pipeline agents in `.harness/agents/` (autonomous). Update the table listing `.claude/agents/` to reference `agents/` instead.
- [ ] 4.2 In `CLAUDE.md`, update any references to `.claude/skills/` or `.claude/commands/opsx/` to reference the plugin `skills/` directory and `/action:` namespace.
- [ ] 4.3 In `HARNESS.md`, update any skill invocation references to use the `/action:` prefix if they reference the old `/opsx:` names.
- [ ] 4.4 Search the codebase (`grep -rn 'opsx:' src/ tests/ .harness/`) for any references to old skill names in Python code or agent prompts. Update any found to use the `/action:` prefixed names.

## 5. Verify Pipeline Agents Unchanged

- [ ] 5.1 Verify `.harness/agents/` still contains all pipeline agent definitions: `bug-hunter.md`, `test-reviewer.md`, `quality-reviewer.md`, `spec-compliance-reviewer.md`, `openspec-reviewer.md`, `spec-writer.md`, `lead.md`. No files should have been moved or modified.
- [ ] 5.2 Verify `src/action_harness/agents.py` `resolve_harness_agents_dir()` still resolves to `.harness/agents/` — no code changes needed.

## 6. Validation

- [ ] 6.1 Run `uv run pytest -v` — all tests must pass (no code changes, just file moves and reference updates).
- [ ] 6.2 Run `uv run ruff check .` — no lint violations.
- [ ] 6.3 Run `uv run ruff format --check .` — formatting must be clean.
- [ ] 6.4 Run `uv run mypy src/` — no type errors.
- [ ] 6.5 Verify `.claude-plugin/plugin.json` exists and contains valid JSON with `"name": "action"`.
- [ ] 6.6 Verify `skills/` directory contains exactly 5 skill directories: `opsx-propose`, `opsx-apply`, `opsx-review`, `opsx-explore`, `opsx-archive`. Each must contain a `SKILL.md` with valid frontmatter.
- [ ] 6.7 Verify `agents/` directory contains `spec-reviewer.md`.
- [ ] 6.8 Verify `.claude/skills/`, `.claude/commands/opsx/`, and `.claude/agents/` do NOT exist.
- [ ] 6.9 Verify `.harness/agents/` still contains all 7 pipeline agent files.
