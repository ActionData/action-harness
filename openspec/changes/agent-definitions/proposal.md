## Why

Review agent prompts are hardcoded as Python strings in `review_agents.py` and `openspec_reviewer.py`. These are simplified "point-in-time copies" of richer global agent definitions in `~/.claude/agents/`. The hardcoded versions have diverged — the global agents have detailed "How to work" sections, output format specs, and rules that the harness versions lack. Tuning an agent requires editing Python source, and there's no way for a target repo to customize what its reviewers look for.

Moving agent definitions to markdown files in `.harness/agents/` makes them versionable, tunable without code changes, and overridable per repo.

## What Changes

- Create `.harness/agents/` directory in the harness repo with default agent definition files: `bug-hunter.md`, `test-reviewer.md`, `quality-reviewer.md`, `spec-compliance-reviewer.md`, `openspec-reviewer.md`
- Each file contains the agent persona (what to look for, how to work, rules) with YAML frontmatter (`name`, `description`). Files do NOT include the JSON output format — the harness appends that at dispatch time.
- `review_agents.py` loads agent prompts from files instead of hardcoded strings. Load order: target repo `.harness/agents/<name>.md` first, fallback to harness default `.harness/agents/<name>.md`.
- `openspec_reviewer.py` loads its prompt from `.harness/agents/openspec-reviewer.md` with the same fallback pattern.
- Remove hardcoded `_AGENT_PROMPTS` dict and `REVIEW_SYSTEM_PROMPT` string from Python source.
- The JSON output format (`_JSON_OUTPUT_FORMAT`), generic severity suffix (`_GENERIC_SEVERITY_SUFFIX`), custom severity set (`_AGENTS_WITH_CUSTOM_SEVERITY`), and catalog checklist integration (`load_catalog`/`render_for_reviewer`) all stay in Python — they are the harness's output and dispatch contract, not part of the agent persona.

## Capabilities

### New Capabilities
- `agent-file-loading`: Loading agent persona definitions from `.harness/agents/` markdown files with YAML frontmatter, target repo override support, and fallback to harness defaults.

### Modified Capabilities
- `review-agents`: Agent prompts loaded from files instead of hardcoded strings. `build_review_prompt` reads from disk with repo override support. Output format still appended by harness.

## Impact

- New directory `.harness/agents/` with 5 markdown files
- `src/action_harness/review_agents.py` — remove `_AGENT_PROMPTS` dict, add file loading with fallback logic, keep `_JSON_OUTPUT_FORMAT`, `_GENERIC_SEVERITY_SUFFIX`, `_AGENTS_WITH_CUSTOM_SEVERITY`, and catalog integration
- `src/action_harness/openspec_reviewer.py` — remove `REVIEW_SYSTEM_PROMPT` string, add file loading with fallback
- `src/action_harness/pipeline.py` — pass repo path to prompt loading functions
- Target repos can optionally place `.harness/agents/<name>.md` to override defaults
