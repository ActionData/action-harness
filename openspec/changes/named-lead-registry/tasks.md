# Tasks: named-lead-registry

## 1. LeadState Model and Registry Module

- [ ] 1.1 Create `src/action_harness/lead_registry.py` with the `LeadState` Pydantic BaseModel. Fields: `name: str`, `repo_name: str`, `purpose: str`, `created_at: str`, `last_active: str`, `session_id: str`, `clone_path: str | None`, `repo_path: str`. Import `BaseModel` from `pydantic`.

- [ ] 1.2 In `lead_registry.py`, implement `derive_repo_name(repo_path: Path, harness_home: Path) -> str`. Logic: (1) check if `repo_path.resolve()` is relative to `harness_home.resolve() / "projects"` — if so, the repo name is `repo_path.parent.name` (matching `_is_managed_repo` pattern in `cli.py:441`); (2) otherwise run `subprocess.run(["git", "-C", str(repo_path), "remote", "get-url", "origin"], capture_output=True, text=True, timeout=120)` and extract the last path component from the URL, stripping `.git` suffix; (3) if subprocess fails (non-zero exit, `FileNotFoundError`, `OSError`, `TimeoutExpired`), fall back to `repo_path.name`. Log each resolution path to stderr via `typer.echo(..., err=True)`.

- [ ] 1.3 In `lead_registry.py`, implement `lead_state_dir(harness_home: Path, repo_name: str, lead_name: str) -> Path` returning `harness_home / "leads" / repo_name / lead_name`. Do NOT create the directory — callers are responsible for `mkdir(parents=True, exist_ok=True)`.

- [ ] 1.4 In `lead_registry.py`, implement `save_lead_state(state: LeadState, harness_home: Path) -> Path`. Compute the state dir via `lead_state_dir`, create it with `mkdir(parents=True, exist_ok=True)`, write `lead.yaml` via `yaml.dump(state.model_dump(), default_flow_style=False)`. Return the path to `lead.yaml`. Use `import yaml` (PyYAML, already a project dependency). Wrap file write in `try/except OSError` and re-raise as `RuntimeError` with the path included.

- [ ] 1.5 In `lead_registry.py`, implement `load_lead_state(harness_home: Path, repo_name: str, lead_name: str) -> LeadState | None`. Read `lead.yaml` from the state dir. Return `None` if the file doesn't exist. Parse via `yaml.safe_load` then `LeadState.model_validate`. Wrap in `try/except (OSError, UnicodeDecodeError, yaml.YAMLError)` and return `None` on failure (log warning to stderr).

- [ ] 1.6 In `lead_registry.py`, implement `list_leads(harness_home: Path, repo_name: str) -> list[LeadState]`. Iterate subdirectories of `harness_home / "leads" / repo_name`, call `load_lead_state` for each. Return only successfully loaded states. Return empty list if the repo directory doesn't exist.

- [ ] 1.7 In `lead_registry.py`, implement `resolve_or_create_lead(harness_home: Path, repo_path: Path, lead_name: str, purpose: str) -> LeadState`. Call `derive_repo_name` to get `repo_name`. Call `load_lead_state`. If existing, update `last_active` to `datetime.now(timezone.utc).isoformat()` and save. If not existing, generate `session_id` via `str(uuid.uuid4())`, set `created_at` and `last_active` to now, set `clone_path` to `None`, set `repo_path` to `str(repo_path.resolve())`, save, and return.

## 2. Lock Management

- [ ] 2.1 In `lead_registry.py`, implement `acquire_lock(harness_home: Path, repo_name: str, lead_name: str, pid: int, session_id: str) -> None`. Lock file path: `lead_state_dir(...) / "lock"`. If lock file exists, read it (format: first line PID, second line session_id). Parse PID as int. Check if alive via `os.kill(pid, 0)` — catch `OSError` (means dead). If alive, raise `RuntimeError(f"Lead '{lead_name}' is already running (PID {existing_pid})")`. If dead, log stale lock warning to stderr. Write new lock file with `f"{pid}\n{session_id}\n"`. Create parent dirs if needed.

- [ ] 2.2 In `lead_registry.py`, implement `release_lock(harness_home: Path, repo_name: str, lead_name: str) -> None`. Delete the lock file if it exists. Wrap in `try/except OSError` and log warning on failure (never raise — this runs in finally blocks).

- [ ] 2.3 In `lead_registry.py`, implement `is_lead_active(harness_home: Path, repo_name: str, lead_name: str) -> bool`. Read the lock file. If it doesn't exist, return `False`. Parse PID, check via `os.kill(pid, 0)`. Return `True` if alive, `False` if dead (and delete the stale lock file).

## 3. Clone Provisioning

- [ ] 3.1 In `lead_registry.py`, implement `provision_clone(state: LeadState, harness_home: Path) -> Path`. Clone destination: `lead_state_dir(harness_home, state.repo_name, state.name) / "clone"`. If destination already exists and is a directory, return it (no re-clone). Determine clone source: run `git -C <state.repo_path> remote get-url origin` — use the URL if available, otherwise use `state.repo_path`. Run `subprocess.run(["git", "clone", source, str(clone_dir)], capture_output=True, text=True, timeout=600)`. On failure, raise `RuntimeError` with stderr included. Return clone path. Include `timeout=600` for large repos.

- [ ] 3.2 Update `resolve_or_create_lead` (task 1.7): add a `provision_clone: bool` parameter (default `False`). When `True` and `lead_name != "default"`, call `provision_clone`, set `state.clone_path = str(clone_path)`, and save the updated state.

## 4. CLI Restructuring

- [ ] 4.1 In `cli.py`, create `lead_app = typer.Typer(name="lead", help="Manage repo lead agents.")` and register it via `app.add_typer(lead_app, name="lead")`. Remove the existing `@app.command()` decorator from the `lead` function.

- [ ] 4.2 Create the `start` subcommand as `@lead_app.callback(invoke_without_command=True)` to handle both `harness lead start ...` and bare `harness lead ...`. Signature: same parameters as current `lead` function, plus `--name` (str, default `"default"`, help: "Lead name — creates a named lead with its own clone") and `--purpose` (str, default `""`, help: "Purpose description for the lead"). Keep all existing parameters (`--repo`, `--interactive/--no-interactive`, `--dispatch`, `--permission-mode`, `--harness-home`, positional `prompt`).

- [ ] 4.3 In the `start` callback body, add lead resolution before context gathering: import and call `resolve_or_create_lead(harness_home=resolved_home, repo_path=repo, lead_name=name, purpose=purpose)` with `provision_clone=(name != "default")`. Determine the effective repo path: if `state.clone_path` is not None and the path exists, use `Path(state.clone_path)` as the repo for context gathering and dispatch; otherwise use the original `repo`.

- [ ] 4.4 In the `start` callback body, wrap the dispatch call (both interactive and non-interactive paths) with lock acquisition and release. Before dispatch: `acquire_lock(harness_home=resolved_home, repo_name=state.repo_name, lead_name=name, pid=os.getpid(), session_id=state.session_id)`. After dispatch (in `finally`): `release_lock(harness_home=resolved_home, repo_name=state.repo_name, lead_name=name)`. Catch `RuntimeError` from `acquire_lock` and exit with code 1, printing the error to stderr.

- [ ] 4.5 In the `start` callback, modify the `dispatch_lead_interactive` call to pass session management. Add `session_id: str | None = None` and `resume: bool = False` parameters to `dispatch_lead_interactive` in `lead.py`. When `resume=True`, insert `--resume <session_id>` into the `claude` command. When `resume=False` and `session_id` is provided, insert `--session-id <session_id>`. In the `start` callback: if the lead already existed (loaded from disk, not freshly created), pass `resume=True, session_id=state.session_id`. If freshly created, pass `resume=False, session_id=state.session_id`.

- [ ] 4.6 Implement resume fallback in `dispatch_lead_interactive`. When `resume=True` and the `claude` process exits with non-zero: generate a new UUID, update the lead state's `session_id` via `save_lead_state`, re-launch with `--session-id <new-uuid>` (without `--resume`), and log the fallback to stderr. Return the exit code from the second attempt.

- [ ] 4.7 Create the `list` subcommand as `@lead_app.command(name="list")`. Parameters: `--repo` (Path, required), `--harness-home` (Path | None, optional). Call `derive_repo_name` then `list_leads`. For each lead, call `is_lead_active` to determine status. Output a table to stdout: columns `Name`, `Purpose`, `Status` (active/idle), `Last Active`, `Clone` (yes/no). If no leads found, print "No leads found for <repo-name>".

- [ ] 4.8 Create the `retire` subcommand as `@lead_app.command()`. Parameters: `name` (str, positional argument), `--repo` (Path, required), `--harness-home` (Path | None, optional). Call `derive_repo_name`, then `load_lead_state`. If state is `None`, exit with error "Lead '<name>' not found for repo <repo-name>". Call `is_lead_active` — if active, exit with error "Cannot retire lead '<name>': currently active (PID <pid>)". Delete the clone directory (if `clone_path` is not None and exists, use `shutil.rmtree`). Delete the lead state directory (`shutil.rmtree`). Print confirmation to stderr.

## 5. Update dispatch_lead_interactive Signature

- [ ] 5.1 In `src/action_harness/lead.py`, update the `dispatch_lead_interactive` function signature to add `session_id: str | None = None` and `resume: bool = False` parameters (after existing parameters). These are keyword-only with defaults so existing callers are unaffected.

- [ ] 5.2 In `dispatch_lead_interactive`, modify the `cmd` list construction. After building the base `cmd` list (line 538-548 of current code), add session management: if `resume` is `True` and `session_id` is not `None`, append `["--resume", session_id]` to `cmd`. Elif `session_id` is not `None`, append `["--session-id", session_id]` to `cmd`. Log which mode was used to stderr.

## 6. Tests

- [ ] 6.1 Create `tests/test_lead_registry.py`. Test `LeadState` model: construct a `LeadState` with all fields, call `model_dump()`, verify all keys present, call `LeadState.model_validate(state.model_dump())` and assert all fields match the original (roundtrip test). Verify `clone_path=None` serializes correctly.

- [ ] 6.2 Test `derive_repo_name` in `test_lead_registry.py`: (a) with a path under `harness_home / "projects" / "my-proj" / "repo"` — assert returns `"my-proj"`; (b) mock `subprocess.run` to return `git@github.com:org/my-app.git` — assert returns `"my-app"`; (c) mock `subprocess.run` to raise `FileNotFoundError` — assert returns the directory basename.

- [ ] 6.3 Test `save_lead_state` and `load_lead_state` in `test_lead_registry.py` using `tmp_path`. Create a `LeadState`, save it, load it back, assert all fields match. Also test `load_lead_state` returns `None` for nonexistent lead.

- [ ] 6.4 Test `list_leads` in `test_lead_registry.py` using `tmp_path`. Save two leads, call `list_leads`, assert returns both. Call `list_leads` for a nonexistent repo, assert returns empty list.

- [ ] 6.5 Test lock management in `test_lead_registry.py`: (a) `acquire_lock` creates lock file with correct content (PID and session_id); (b) `release_lock` deletes the lock file; (c) `acquire_lock` raises `RuntimeError` when lock is held by current process (use `os.getpid()`); (d) `acquire_lock` reclaims stale lock — write a lock file with PID `999999999` (unlikely to be alive), call `acquire_lock`, assert it succeeds; (e) `is_lead_active` returns `False` when no lock, `True` when current PID holds lock.

- [ ] 6.6 Test `provision_clone` in `test_lead_registry.py` using `tmp_path`. Create a bare git repo with `git init`, create a `LeadState` pointing to it, call `provision_clone`. Assert clone directory exists and is a git repo (`(clone_dir / ".git").is_dir()`). Call `provision_clone` again and assert it returns immediately (no error, same path).

- [ ] 6.7 Test `resolve_or_create_lead` in `test_lead_registry.py` using `tmp_path`. (a) First call creates state with correct fields (check `created_at` is set, `session_id` is a UUID). (b) Second call with same name loads existing and updates `last_active` (assert `last_active` changed, `created_at` unchanged, `session_id` unchanged).

- [ ] 6.8 Test CLI `lead list` in `test_lead_registry.py` using `CliRunner`. Mock `derive_repo_name` to return a fixed name. Save two lead states to `tmp_path`. Invoke `lead list --repo /tmp/fake --harness-home <tmp_path>`. Assert exit code 0 and both lead names appear in output.

- [ ] 6.9 Test CLI `lead retire` in `test_lead_registry.py` using `CliRunner`. Save a lead state to `tmp_path`. Invoke `lead retire <name> --repo /tmp/fake --harness-home <tmp_path>`. Assert exit code 0 and the lead directory is deleted. Test retire of nonexistent lead returns exit code 1.

- [ ] 6.10 Test CLI backward compatibility in `test_lead_registry.py`. Mock `dispatch_lead_interactive` and `gather_lead_context`. Invoke `harness lead --repo <tmp_path>` (no `start` subcommand). Assert that `dispatch_lead_interactive` was called (proving the bare command still works).

## 7. Validation

- [ ] 7.1 Run `uv run pytest tests/test_lead_registry.py -v` — all tests pass.
- [ ] 7.2 Run `uv run pytest tests/test_lead.py -v` — existing lead tests still pass (no regressions).
- [ ] 7.3 Run `uv run ruff check src/action_harness/lead_registry.py src/action_harness/lead.py src/action_harness/cli.py` — no lint errors.
- [ ] 7.4 Run `uv run ruff format --check src/action_harness/lead_registry.py src/action_harness/lead.py src/action_harness/cli.py` — properly formatted.
- [ ] 7.5 Run `uv run mypy src/action_harness/lead_registry.py src/action_harness/lead.py` — no type errors.
- [ ] 7.6 Run `uv run pytest -v` — full test suite passes.
