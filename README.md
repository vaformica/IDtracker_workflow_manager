# IDtracker Workflow Manager

This repository is the implementation home for a planned SQLite-backed workflow
manager for Basler videos, IDtracker TOMLs, IDtracker runs, post-processing
runs, and human QC decisions.

The purpose is to stop treating filenames and scattered IDtracker session
folders as the source of truth. The central unit will be a stable
`tracking_target_id`: one intended video/cell/analysis target.

## Current status

Stage 0 is a developer bootstrap only. The repository currently provides an
importable Python package and a smoke-test runner. It does **not** yet implement
the SQLite registry, workflow stages, GUIs, or scientific-data handling.

Implementation must proceed one stage at a time according to
[`planning/STAGE_EXECUTION_PLAN.md`](planning/STAGE_EXECUTION_PLAN.md). The
complete design is in
[`planning/IDTRACKER_WORKFLOW_MANAGER_PLAN.md`](planning/IDTRACKER_WORKFLOW_MANAGER_PLAN.md).

## Requirements

- Python 3.10 or newer
- `make` (optional; the underlying test command can be run directly)

The Stage 0 package has no third-party runtime dependencies.

## Setup

Create and activate a virtual environment from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --editable .
```

An editable install makes the `src/` package importable while it is under
development.

## Run tests

```bash
make test
```

Or run the dependency-free test command directly:

```bash
python3 -m unittest discover -s tests -v
```

The Stage 0 smoke test verifies that `idtracker_workflow_manager` imports and
exposes its version.

## Repository layout

```text
IDtracker_workflow_manager/
  planning/                         staged design and execution plans
  src/idtracker_workflow_manager/   Python package
  tests/                            focused automated tests
  AGENTS.md                         repository-specific developer constraints
  Makefile                          common developer commands
  pyproject.toml                    package metadata and build configuration
```

Modules and GUI directories described in the long-term plan should be added
only when their implementation stage begins.

## Staged development rules

- Implement only the requested stage; do not pull later-stage features forward.
- Keep SQLite as the future source of truth. CSV files will be exports and
  reports, not authoritative data.
- Preserve scientific provenance and never silently overwrite history.
- Treat filename-derived identity as provisional rather than authoritative.
- Treat other repositories, including `One_script_to_rule_them_all`, as
  read-only unless a request explicitly says otherwise.
- End each stage with focused tests, a worktree review, documentation updates
  when behavior changes, and a Git commit.
