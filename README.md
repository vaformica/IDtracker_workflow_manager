# IDtracker Workflow Manager

This repository is the implementation home for a planned SQLite-backed workflow
manager for Basler videos, IDtracker TOMLs, IDtracker runs, post-processing
runs, and human QC decisions.

The purpose is to stop treating filenames and scattered IDtracker session
folders as the source of truth. The central unit will be a stable
`tracking_target_id`: one intended video/cell/analysis target.

## Current status

Stage 2 adds video intake and full-resolution PNG still generation to the
SQLite registry core. It provides a basic desktop GUI, per-video type labels,
an explicit frame fallback sequence, recorded success/failure metadata, and an
updated videos CSV export. It does **not** yet implement occupied-cell
selection, a target-creation GUI, TOML handling, IDtracker execution,
post-processing, or QC.

Implementation must proceed one stage at a time according to
[`planning/STAGE_EXECUTION_PLAN.md`](planning/STAGE_EXECUTION_PLAN.md). The
complete design is in
[`planning/IDTRACKER_WORKFLOW_MANAGER_PLAN.md`](planning/IDTRACKER_WORKFLOW_MANAGER_PLAN.md).

## Authoritative post-processing code

For post-processing behavior, the current best implementation is the latest
code in:

```text
/Users/New/Library/CloudStorage/Dropbox/Projects/Coding_Repositories/IDtracker_postprocessing_prototype
```

When this workflow manager reaches post-processing integration, use that repo's
latest `processor.py`, `firebird_gui.py`, `combine_results.py`,
`slurm_worker.py`, `slurm_finalize.py`, `postprocessing_qc.py`, tests, README,
METHODS, and DATA_DICTIONARY as the authoritative reference. Do not resurrect
older post-processing code from `One_script_to_rule_them_all`, old temporary
Codex folders, or earlier CSV/PDF scripts unless it is being used only as
historical context.

The workflow manager may eventually absorb or wrap the latest post-processing
prototype, but until that migration is explicitly implemented and tested, the
standalone prototype is the scientifically preferred post-processing code.

## Requirements

- Python 3.10 or newer
- `make` (optional; the underlying test command can be run directly)

The Stage 2 Python package has no third-party runtime dependencies. Still
generation requires an external `ffmpeg` executable available on `PATH`.

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

The test suite covers package import, schema creation, video upserts, stable
IDs, duplicate-target rejection, foreign-key relationships, CSV exports,
ffmpeg command construction, fallback behavior, and still metadata updates.

## Video intake GUI

After completing setup, launch:

```bash
idtracker-video-intake
```

Or run directly from the source checkout:

```bash
PYTHONPATH=src python3 -m idtracker_workflow_manager.video_intake
```

Default runtime paths, relative to the directory where the GUI is launched:

```text
idtracker_workflow.sqlite
stills/frame_2000/
exports/videos.csv
```

Use command-line options to change them:

```bash
idtracker-video-intake \
  --database /path/to/idtracker_workflow.sqlite \
  --stills /path/to/stills/frame_2000 \
  --video-export /path/to/exports/videos.csv \
  --ffmpeg /path/to/ffmpeg
```

In the GUI:

1. Enter the operator name.
2. Choose `ba`, `fight`, `other`, or `unknown`.
3. Add one or more videos. Each row retains its assigned type; select rows and
   use **Set type on selected** to change individual assignments.
4. Select **Register and generate stills**.

The table shows each successful still path and actual frame number. Failed
videos remain registered with `still_generation_status = FAILED` and the
ffmpeg error in SQLite so they can be addressed without guessing.

### Still fallback

The still generator applies no scaling filter, so the PNG retains the source
video resolution. It tries:

1. frame 2000;
2. frame 1000;
3. frame 0, representing the first valid frame.

The generated filename contains the actual frame number, and SQLite records
`still_frame_number`, `still_png_path`, `still_created_at`,
`still_generation_status`, and `still_generation_error`. A failed later
attempt does not erase metadata for an earlier successful still.

## Registry core

Initialize a registry and add a video and tracking target:

```python
from idtracker_workflow_manager import (
    create_tracking_target,
    initialize_database,
    upsert_video,
)

database_path = "idtracker_workflow.sqlite"
initialize_database(database_path)

video = upsert_video(
    database_path,
    "/absolute/path/Camera_2_example.mp4",
    video_type="fight",
    video_type_source="manual",
    created_by="researcher-name",
)

target = create_tracking_target(
    database_path,
    video["video_id"],
    "B3",
    "fight",
    created_by="researcher-name",
)
```

`initialize_database()` is idempotent. It creates the `videos` and
`tracking_targets` tables, enables their foreign-key relationship, and applies
safe additive columns needed by the current stage.

### Stable identity and duplicates

- `video_id` is a deterministic UUIDv5 derived from the normalized absolute
  video path.
- `tracking_target_id` is a deterministic UUIDv5 derived from `video_id`, the
  uppercased cell label, and the lowercased analysis type.
- SQLite enforces one row per `video_path`.
- SQLite enforces one target per `(video_id, cell_label, analysis_type)`.
- `create_tracking_target()` raises `DuplicateTrackingTargetError` rather than
  silently merging an existing target.

Changing TOML settings or rerunning later workflow stages must not create a new
tracking target. Those attempts will receive their own version/run records in
later implementation stages.

### CSV exports

```python
from idtracker_workflow_manager import (
    export_tracking_targets_csv,
    export_videos_csv,
)

export_videos_csv(database_path, "exports/videos.csv")
export_tracking_targets_csv(
    database_path,
    "exports/tracking_targets.csv",
)
```

Exports include headers even when a table is empty and use deterministic row
ordering. They are human-readable reports; SQLite remains authoritative.

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

Modules and GUI directories described in the long-term plan will be added only
when their implementation stage begins.

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
