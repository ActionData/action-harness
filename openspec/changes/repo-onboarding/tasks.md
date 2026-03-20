## 1. Gap Detection

- [ ] 1.1 Create `src/action_harness/onboarding.py` with `OnboardingGaps` Pydantic model containing fields: `openspec_initialized: bool`, `harness_md_exists: bool`, `project_registered: bool`, and computed `has_gaps: bool` property
- [ ] 1.2 Implement `detect_gaps(repo_path: Path, harness_home: Path | None) -> OnboardingGaps` that checks for `openspec/` dir, `HARNESS.md` file, and `config.yaml` in the project directory
- [ ] 1.3 Add tests for `detect_gaps()` covering fully onboarded, completely un-onboarded, and partially onboarded repos

## 2. Gap Filling

- [ ] 2.1 Implement `_scaffold_openspec(repo_path: Path) -> bool` that runs `openspec init --tools claude` as a subprocess, returns success/failure, handles `FileNotFoundError` when openspec CLI is not installed
- [ ] 2.2 Implement `_scaffold_harness_md(repo_path: Path) -> bool` that calls `profile_repo()` to detect eval commands, writes a `HARNESS.md` with those commands and an auto-detected comment
- [ ] 2.3 Implement `_register_project(repo_path: Path, harness_home: Path) -> bool` that calls `ensure_project_dir()` and `write_project_config()` to register the repo
- [ ] 2.4 Implement `fill_gaps(repo_path: Path, harness_home: Path | None, gaps: OnboardingGaps) -> OnboardingResult` that calls each scaffold function only for missing components and returns a structured result with per-component outcomes
- [ ] 2.5 Add tests for `fill_gaps()` covering each scaffold function individually and the idempotent skip behavior

## 3. CLI Command

- [ ] 3.1 Add `harness onboard` command to `cli.py` with `--repo`, `--yes`, and `--harness-home` options
- [ ] 3.2 Implement the command flow: resolve repo, detect gaps, display gap report, prompt for confirmation (unless `--yes`), fill gaps, display summary
- [ ] 3.3 Handle the no-gaps case: display "repo is fully onboarded" and exit 0
- [ ] 3.4 Add completion summary suggesting `harness lead --repo <path>` for roadmap and priority setup

## 4. Lead Integration

- [ ] 4.1 Add `onboarding_gaps: OnboardingGaps | None` field to `LeadContext` dataclass
- [ ] 4.2 Call `detect_gaps()` in `gather_lead_context()` and populate the new field
- [ ] 4.3 Include onboarding gap information in `LeadContext.full_text` when gaps exist, formatted as a "## Onboarding Status" section
- [ ] 4.4 Update the lead persona in `.harness/agents/lead.md` to mention onboarding capability: when gaps are detected in context, offer to run `harness onboard` before proceeding
- [ ] 4.5 Add tests verifying `gather_lead_context()` populates `onboarding_gaps` correctly
