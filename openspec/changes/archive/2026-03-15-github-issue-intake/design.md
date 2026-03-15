## Context

The harness accepts work via `--change` (OpenSpec change) or `--prompt` (freeform task, from `unspecced-tasks`). GitHub issues are a natural third intake path. The operator points the harness at an issue, and it figures out what to do.

This depends on `unspecced-tasks` being implemented (for the `--prompt` fallback path). If `unspecced-tasks` hasn't landed yet, issue intake can only handle issues that reference an existing OpenSpec change.

## Goals / Non-Goals

**Goals:**
- `--issue <number>` flag on `harness run`
- Read issue via `gh issue view <number> --json title,body,labels`
- Detect OpenSpec change references in the issue body (e.g., `openspec:change-name` or `change: change-name`)
- If change reference found, dispatch as `--change`; otherwise dispatch as `--prompt`
- PR body includes `Closes #<number>` for automatic issue closure
- Label issue with status updates (`harness:in-progress`, `harness:pr-created`)

**Non-Goals:**
- Webhook-based intake (that's `always-on`)
- Creating OpenSpec changes from issues (that's a future capability)
- Handling multiple issues in one run
- Issue triage or priority sorting
- Reacting to issue comments or updates

## Decisions

### 1. `--issue` is mutually exclusive with `--change` and `--prompt`

The three flags form a three-way mutual exclusion: exactly one must be provided. `--issue` determines the mode internally (change or prompt) based on issue content.

### 2. OpenSpec change reference detection

The harness scans the issue body for patterns:
- `openspec:change-name` (inline reference)
- `change: change-name` (YAML-style)
- `openspec/changes/change-name` (path reference)

If a match is found AND the change directory exists in the repo (`openspec/changes/<name>/`), use `--change` mode. Otherwise, fall back to `--prompt` mode with the issue title + body.

**Alternative considered:** Using issue labels to indicate the change name. Rejected — labels require manual setup and don't carry the change name naturally. Body parsing is more flexible.

### 3. Prompt construction from issue

When no OpenSpec change is referenced, the prompt is constructed as:
```
# GitHub Issue #{number}: {title}

{body}
```

This gives the worker the full issue context. The title becomes the PR title via `[harness] {title}`.

### 4. PR links to issue

When dispatched from an issue, the PR body includes `Closes #<number>` so GitHub automatically closes the issue when the PR is merged. The issue number is passed through the pipeline as metadata.

### 5. Issue status labels

The harness labels the issue at key stages:
- `harness:in-progress` — set when the pipeline starts
- `harness:pr-created` — set when the PR is created (includes PR URL in a comment)
- Labels are best-effort — failure to label does not fail the pipeline

### 6. Issue reading via `gh issue view`

Uses `gh issue view <number> --json title,body,labels,state` in the repo's working directory. Requires `gh` CLI authenticated with issue read permissions (already validated at pipeline start).

## Risks / Trade-offs

- [Issue format] Issues with vague descriptions will produce poor results → Mitigation: same as `--prompt` — the eval gate catches bad implementations
- [Change reference false positive] Issue body mentions a change name that doesn't exist → Mitigation: verify the change directory exists before using `--change` mode. Fall back to `--prompt`.
- [Label permissions] The harness needs write access to add labels → Mitigation: label operations are best-effort. Missing permissions log a warning.
- [Depends on unspecced-tasks] Without `--prompt` mode, issues without change references can't be dispatched → Mitigation: document the dependency. If `unspecced-tasks` isn't implemented, those issues get an error message.
