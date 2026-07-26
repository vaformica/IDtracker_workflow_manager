# Repository Guidance

## Scope

- Work only in this repository unless the user explicitly expands the scope.
- Implement one stage at a time from `planning/STAGE_EXECUTION_PLAN.md`.
- Do not implement functionality assigned to a later stage.
- Treat existing related repositories as read-only references.
- Never modify `One_script_to_rule_them_all` from this repository's work.

## Architecture and scientific safeguards

- SQLite is the planned source of truth; CSV files are exports and reports.
- The central workflow identity is `tracking_target_id`.
- Preserve provenance and history. Do not silently overwrite, discard, merge,
  or infer scientific records.
- Treat filename parsing as provisional evidence, not authoritative identity.
- Keep raw inputs untouched.

## Development

- Support Python 3.10 or newer.
- Keep package code under `src/idtracker_workflow_manager/`.
- Keep focused automated tests under `tests/`.
- Prefer the standard library until a stage has a clear need for a dependency.
- Run `make test` (or the equivalent documented command) before committing.
- Update documentation when behavior or developer setup changes.
- Review `git status` and the complete diff before each stage commit.
