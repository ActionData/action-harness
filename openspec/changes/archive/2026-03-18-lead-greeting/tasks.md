## 1. Update Lead Persona Prompt

- [ ] 1.1 In `.harness/agents/lead.md`, add a role statement paragraph to the Interactive Mode section that explains the lead is the human's interface to the harness pipeline — the repo expert that coordinates implementation, planning, and analysis
- [ ] 1.2 Add a "What I Can Help With" subsection to Interactive Mode that lists capability categories organized by user intent: **Build** (implement GitHub issues via `harness run --issue`, dispatch ready OpenSpec changes), **Plan** (explore ideas, create OpenSpec proposals via `opsx:propose`, design features), **Understand** (answer repo questions, analyze code, review assessment scores and failure patterns)
- [ ] 1.3 Update the greeting example to demonstrate the enhanced structure: role sentence → current state summary → 2-3 capability-aware suggestions that span different categories → open prompt. Keep the example under 25 lines
- [ ] 1.4 Add guidance that suggested directions should span at least two capability categories (not all implementation or all exploration) and reference specific items from the gathered context (change names, issue numbers, assessment scores)

## 2. Validation

- [ ] 2.1 Run `uv run pytest -v` — all tests pass
- [ ] 2.2 Run `uv run ruff check .` — no lint violations
- [ ] 2.3 Run `uv run ruff format --check .` — formatting clean
- [ ] 2.4 Run `uv run mypy src/` — no type errors
- [ ] 2.5 Verify the updated persona prompt is well-formed markdown and does not exceed reasonable length (the Interactive Mode section should stay under ~80 lines)
