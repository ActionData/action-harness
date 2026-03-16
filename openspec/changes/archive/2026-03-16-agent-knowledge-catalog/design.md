## Context

The harness has quality rules in CLAUDE.md and HARNESS.md for this repo. But these are static text — they don't adapt to the target repo's ecosystem, and review agents don't have a structured checklist. The catalog formalizes the knowledge into structured entries that can be filtered, rendered differently for different consumers, and tracked per repo.

See `docs/research/agent-quality-catalog.md` for the three-layer context hierarchy and the full analysis.

## Goals / Non-Goals

**Goals:**
- YAML catalog entries with: id, class, severity, ecosystems, worker_rule, reviewer_checklist, assessment scan, examples, provenance
- Loader that filters by ecosystem (from `profile_repo()`)
- Renderer that produces 3 formats: worker rules (concise, top N), reviewer checklist (detailed), assessment criteria
- Inject worker rules into the worker system prompt at dispatch time
- Inject reviewer checklist into review agent system prompts
- Per-repo finding frequency store in harness home

**Non-Goals:**
- RAG or vector database (structured JSON is sufficient at current scale — see research doc for trigger conditions)
- Auto-generating catalog entries from review findings (future enhancement)
- Web UI for browsing the catalog
- Custom catalog entries per repo (that's HARNESS.md — the catalog is universal/ecosystem-level)

## Decisions

### 1. YAML entries in `src/action_harness/catalog/entries/`

Each entry is a YAML file:
```yaml
id: subprocess-timeout
class: defensive-io
severity: high
ecosystems: [python]
worker_rule: "Every subprocess.run() must include timeout="
reviewer_checklist:
  - "Check all subprocess.run calls have timeout="
  - "Check except clauses include subprocess.TimeoutExpired"
examples:
  bad: "subprocess.run(cmd, capture_output=True)"
  good: "subprocess.run(cmd, capture_output=True, timeout=120)"
learned_from:
  - pr: "#34"
    finding: "No subprocess timeout on gh CLI calls"
```

YAML is human-readable and editable. The scanner logic (for assessment scoring) is in Python, not YAML — YAML entries are documentation and prompt content.

### 2. Loader filters by ecosystem, sorts by severity

```python
catalog = load_catalog(ecosystem="python")  # returns entries for python + "all"
worker_rules = catalog.render_for_worker(top_n=10)
reviewer_checklist = catalog.render_for_reviewer()
```

Entries with `ecosystems: [all]` are always included. Entries with specific ecosystems are included only when the repo's ecosystem matches.

### 3. Worker gets top 10 rules, reviewer gets full checklist

The worker prompt has limited budget — every rule competes with implementation context. Top 10 rules by severity, rendered as a concise bulleted list (~500 bytes).

Review agents have more budget — they're read-only. Full checklist with examples (~3KB).

### 4. Per-repo finding frequency in harness home

```
~/.harness/repos/<repo>/knowledge/findings-frequency.json
{
  "subprocess-timeout": {"count": 4, "last_seen": "2026-03-15"},
  "bare-assert": {"count": 2, "last_seen": "2026-03-14"}
}
```

After each review round, classify findings against catalog entries and increment counters. On subsequent runs, entries with high frequency for this repo get boosted in worker rule selection (the repo's "hot rules").

### 5. Injection points

Worker dispatch (`worker.py`): after building the system prompt and injecting HARNESS.md, append the catalog worker rules section.

Review agent dispatch (`review_agents.py`): append the catalog reviewer checklist to each review agent's system prompt via `build_review_prompt`.

Both injection points already exist — HARNESS.md is injected into the worker prompt, and `build_review_prompt` builds the review agent system prompt. The catalog adds content to these existing injection points.

## Risks / Trade-offs

- [Prompt bloat] Catalog rules add to the system prompt → Mitigation: worker gets only top 10 (~500 bytes). Reviewer gets full checklist (~3KB) which is within budget.
- [False rules] A catalog entry could give wrong advice for a specific repo → Mitigation: entries are filtered by ecosystem. Repo-specific exceptions go in HARNESS.md, not the catalog.
- [Stale frequency data] Finding frequency may not reflect current repo state → Mitigation: frequency is a boost signal, not a gate. Stale data slightly over-prioritizes a rule but doesn't cause incorrect behavior.
