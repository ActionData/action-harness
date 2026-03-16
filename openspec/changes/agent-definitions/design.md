## Context

The harness dispatches 5 agents: bug-hunter, test-reviewer, quality-reviewer, spec-compliance-reviewer (via `review_agents.py`) and openspec-reviewer (via `openspec_reviewer.py`). All prompts are currently hardcoded Python strings. Richer versions exist in `~/.claude/agents/` but have diverged from the hardcoded copies. The harness appends a shared JSON output format suffix to review agent prompts at dispatch time.

## Goals / Non-Goals

**Goals:**
- Agent personas as versionable markdown files in `.harness/agents/`
- Target repos can override agent personas by placing files in their own `.harness/agents/`
- Richer agent definitions (ported from `~/.claude/agents/`) with detailed instructions
- Output format contract stays in Python — persona files don't include it

**Non-Goals:**
- Per-agent model/effort/max-turns configuration via frontmatter (future enhancement)
- New agent types beyond the existing 5
- Changing what the agents actually review (that's a separate prompt-tuning effort)

## Decisions

### 1. File format: markdown with YAML frontmatter

```markdown
---
name: bug-hunter
description: Deep bug-finding specialist...
---

You are a bug-finding specialist...
```

The frontmatter provides metadata. The body is the prompt text. This matches the format already used by `~/.claude/agents/` and Claude Code's native agent loading.

**Rationale:** Consistent with existing conventions. Frontmatter is extensible — future fields like `model`, `max-turns`, `effort` can be added without format changes.

### 2. Persona only — harness appends output format

Agent files define what to look for and how to work. The harness appends the JSON output format at dispatch time. This keeps the output contract in one place (`_JSON_OUTPUT_FORMAT`, `_GENERIC_SEVERITY_SUFFIX`, and `_AGENTS_WITH_CUSTOM_SEVERITY` in `review_agents.py`; the JSON block instructions in `openspec_reviewer.py`). The catalog checklist integration (`load_catalog`/`render_for_reviewer`) also stays in Python — it's appended after the output format.

**Rationale:** If we change the findings JSON schema, we update it once in Python. Agents don't need to know or care about the output format — they just do the review.

**Alternative considered:** Full prompt in agent files. Rejected because it duplicates the output format across 4 review agent files and makes schema changes error-prone.

**What stays in Python for review agents:** `_JSON_OUTPUT_FORMAT` (JSON schema), `_GENERIC_SEVERITY_SUFFIX` (generic severity definitions — appended unless the agent is in `_AGENTS_WITH_CUSTOM_SEVERITY`), and the catalog checklist (appended via `load_catalog`/`render_for_reviewer` based on ecosystem). Agents with custom severity definitions (currently `spec-compliance-reviewer`) define their own severity scale in their persona file and are excluded from the generic suffix.

### 3. Load order: target repo overrides harness defaults

```python
def load_agent_prompt(agent_name: str, repo_path: Path, harness_agents_dir: Path) -> str:
    # 1. Target repo override
    repo_agent = repo_path / ".harness" / "agents" / f"{agent_name}.md"
    if repo_agent.exists():
        return parse_agent_body(repo_agent)

    # 2. Harness default
    default_agent = harness_agents_dir / f"{agent_name}.md"
    if default_agent.exists():
        return parse_agent_body(default_agent)

    raise FileNotFoundError(f"No agent definition found for '{agent_name}'")
```

**Rationale:** Repos can customize reviewers for their domain (e.g., a database project might want the bug-hunter to focus on SQL injection). Defaults always work out of the box.

**harness_agents_dir:** The resolved path to the directory containing default agent files. `resolve_harness_agents_dir()` returns this — when running from source it's `<repo_root>/.harness/agents/`, when installed as a package it resolves via `importlib.resources`.

### 4. Frontmatter parsing

Use `pyyaml` (already a dependency) to parse frontmatter. Simple split on `---` delimiters, parse the YAML block, return the body text after the closing `---`.

```python
def parse_agent_file(path: Path) -> tuple[dict[str, str], str]:
    """Parse frontmatter and body from an agent markdown file."""
    content = path.read_text()
    if not content.startswith("---"):
        return {}, content  # no frontmatter, entire content is prompt
    parts = content.split("---", 2)
    meta = yaml.safe_load(parts[1]) or {}
    body = parts[2].strip()
    return meta, body
```

### 5. OpenSpec reviewer prompt structure

The openspec-reviewer is different from review agents — it has dynamic content (change name templated into the prompt) and harness-specific instructions (run `openspec validate`, archive). The file contains the prompt template with `{change_name}` placeholders. The harness reads the file and calls `.format(change_name=name)` before dispatch.

The JSON output block for the openspec reviewer stays appended by the harness (same pattern as review agents).

### 6. Default agent file locations

Default agent files ship with the harness package at `.harness/agents/` relative to the repo root. This directory is checked into the action-harness repo.

```
action-harness/
├── .harness/
│   ├── agents/
│   │   ├── bug-hunter.md
│   │   ├── test-reviewer.md
│   │   ├── quality-reviewer.md
│   │   ├── spec-compliance-reviewer.md
│   │   └── openspec-reviewer.md
│   └── protected-paths.yml
└── src/
    └── action_harness/
```

**Rationale:** `.harness/` is already the convention for harness configuration. Agents live alongside `protected-paths.yml`.

### 7. Packaging strategy

For installed-as-package support, copy agent files into `src/action_harness/default_agents/` at build time, or use hatch's `force-include` to bundle `.harness/agents/` into the wheel. The `resolve_harness_agents_dir()` function tries the source checkout path first (`.harness/agents/` relative to repo root), then falls back to `importlib.resources.files("action_harness") / "default_agents"`.

**Rationale:** Agent files must be available whether running from source or installed. The dual-path resolution handles both cases. The source checkout is the primary path (development and self-hosting); the package path is the fallback for external installations.

### 8. OpenSpec reviewer JSON block escaping

The openspec-reviewer prompt template uses `{change_name}` placeholders. When extracting the JSON output block into `_OPENSPEC_JSON_SUFFIX`, the braces in the JSON example must be literal (not escaped with `{{`/`}}`), because the suffix is appended AFTER `.format(change_name=...)` is called on the persona text. The persona file uses `{change_name}` for templating; the JSON suffix has no placeholders and is concatenated post-format.

## Risks / Trade-offs

**[File I/O on every dispatch]** → Each agent dispatch reads a file from disk. Mitigation: files are small (<2KB), read once per dispatch, and filesystem caching makes this negligible.

**[Resolving harness repo path when installed as package]** → When installed via `pip`/`uv`, the harness repo root isn't on disk in the expected location. Mitigation: use `importlib.resources` to locate the package's `.harness/agents/` directory, or bundle defaults as a fallback dict in Python (last resort).

**[Repo override could break output format]** → A repo could override an agent with a prompt that doesn't produce parseable findings. Mitigation: the output format is appended by the harness, not part of the agent file. The agent persona can't break the format unless it explicitly contradicts the appended instructions.

**[Frontmatter parsing edge cases]** → Files without frontmatter, malformed YAML, or missing `---` delimiters. Mitigation: `parse_agent_file` handles missing frontmatter gracefully (treats entire content as prompt body).
