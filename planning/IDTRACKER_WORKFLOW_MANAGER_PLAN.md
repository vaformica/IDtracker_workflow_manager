# IDtracker Workflow Manager Implementation Plan

Version: planning draft 2026-07-25

## 1. Purpose

Build a new standalone repository for managing the full beetle video tracking
workflow from Basler video intake through final approved analysis data.

The new system should solve the current data-management problems:

- TOML filenames are carrying too much biological/workflow identity.
- IDtracker creates session folders in video directories, causing clutter and
  orphaned runs.
- Difficult videos/cells can be rerun many times without a clear target-level
  history.
- Old approval filtering may have excluded too much data.
- Post-processing outputs, rejected runs, rerun needs, and final approved data
  need human-readable provenance.

The new system should remain backwards compatible with existing 2025 and 2026
data. It should be able to import old TOMLs, existing session folders, old
post-processing outputs, and scattered Firebird folders without requiring the
old data to be reorganized first.

## 2. High-Level Architecture

Use one new repository:

```text
IDtracker_workflow_manager
```

Do not split the first implementation into three separate repos. The stages are
too interrelated, and separate repos would duplicate Firebird path logic,
session discovery logic, ID generation, and provenance rules.

Instead, build one repository with separate modules/GUIs:

```text
IDtracker_workflow_manager/
  workflow_registry/
  video_intake_gui/
  toml_import_gui/
  idtracker_runner_gui/
  postprocessing_gui/
  qc_review_gui/
  planning/
  tests/
```

The shared registry/database is the source of truth. The GUIs are views/actions
on that registry.

## 3. Source Of Truth

Use SQLite as the source of truth:

```text
idtracker_workflow.sqlite
```

Do not use FileMaker as the core data store. FileMaker could be useful for
forms, but it would make HPC integration, scripted audits, Git versioning, and
R reproducibility harder.

Do not use loose CSVs as the source of truth. CSVs should be exports and
reports. SQLite should enforce relationships, uniqueness, and history.

SQLite advantages:

- portable single file;
- no server;
- works on Mac and Firebird;
- easy backup;
- Python support through `sqlite3`;
- R support through `DBI` and `RSQLite`;
- can export clean CSVs for students and R;
- can enforce uniqueness and foreign-key relationships.

## 4. Central Concept: Tracking Target

The central unit is:

```text
tracking_target_id
```

A tracking target represents one intended video/cell/analysis combination.

Conceptually:

```text
tracking_target_id = video + cell_label + analysis_type
```

Example:

```text
Camera_2_40359705_20260701_1336_FIGHT_ACT1.mp4 | B3 | fight
```

The target exists before IDtracker runs.

Everything attaches to this target:

- TOML versions;
- IDtracker runs;
- post-processing runs;
- QC decisions;
- final approved data;
- rerun reports;
- exclusion reports.

This prevents a difficult video/cell from becoming ten unrelated session
folders.

## 5. Workflow Stages

Long-term model:

```text
Basler video
  -> still PNG at frame 2000
  -> user-selected occupied cells
  -> tracking targets
  -> TOML versions
  -> IDtracker runs
  -> post-processing runs
  -> QC decisions
  -> approved final data
```

The user should not need to enter beetle biological IDs in the fight room.
During intake, the minimum metadata is:

- video path;
- broad video type: `ba`, `fight`, or `other`;
- occupied cell labels;
- creator;
- timestamp.

Beetle biological IDs can be joined later from separate biological metadata.

## 6. Firebird Registry Folder

Create one central Firebird workflow folder:

```text
/data/labs/vformic1-swat-lab/idtracker_workflow_registry/
```

Suggested structure:

```text
idtracker_workflow_registry/
  database/
    idtracker_workflow.sqlite
    backups/
  tomls/
    active/
    archived/
    superseded/
  stills/
    frame_2000/
  reports/
    approved_final/
    needs_idtracker_rerun/
    needs_postprocessing_rerun/
    needs_start_time/
    excluded/
    duplicates/
    orphan_sessions/
  logs/
  exports/
```

The registry folder is the central intake and provenance location. Existing
videos and IDtracker session folders do not need to be moved into it.

## 7. Database Schema

### 7.1 `videos`

One row per Basler recording.

Suggested fields:

```text
video_id
video_path
video_filename
video_stem
video_type
video_type_source
camera
camera_id
recording_date
recording_time
act
year
possible_cell_layout
still_frame_number
still_png_path
still_created_at
created_at
updated_at
created_by
notes
```

`video_type` should be selected by the user when possible:

```text
ba
fight
other
unknown
```

For existing data, filename parsing can create a draft value, but it should be
marked as inferred.

### 7.2 `tracking_targets`

One row per actual video/cell/analysis target.

Suggested fields:

```text
tracking_target_id
video_id
video_path
video_filename
cell_label
analysis_type
target_source
target_status
created_at
created_by
updated_at
current_toml_version_id
current_idtracker_run_id
current_postprocessing_run_id
current_qc_decision_id
final_approved
notes
```

`target_source` examples:

```text
manual_cell_selection
imported_existing_toml
imported_existing_session
recovered_orphan_session
```

`target_status` examples:

```text
TARGET_CREATED
NEEDS_TOML
TOML_READY
IDTRACKER_READY_TO_RUN
IDTRACKER_RUNNING
IDTRACKER_RUN_COMPLETE
IDTRACKER_RERUN_REQUESTED
POSTPROCESSING_READY
POSTPROCESSING_COMPLETE_REVIEW_NEEDED
POSTPROCESSING_RERUN_REQUESTED
QC_APPROVED
QC_REJECT_EXCLUDE_FROM_ANALYSIS
QC_NEEDS_START_TIME
QC_IDENTITY_INCOMPLETE
QC_DUPLICATE_SUPERSEDED
```

Unique constraint:

```text
video_id + cell_label + analysis_type
```

This prevents accidentally creating multiple biological/workflow targets for
the same video/cell/analysis.

### 7.3 `toml_versions`

One row per TOML/settings version for a target.

Suggested fields:

```text
toml_version_id
tracking_target_id
toml_registry_path
original_toml_path
sidecar_metadata_path
toml_hash
toml_version_number
is_current
created_at
created_by
imported_at
import_method
match_confidence
match_evidence
settings_summary_json
notes
```

Important rule:

Same video/cell/analysis with changed TOML settings remains the same
`tracking_target_id`, but gets a new `toml_version_id`.

### 7.4 `idtracker_runs`

One row per IDtracker attempt.

Suggested fields:

```text
idtracker_run_id
tracking_target_id
toml_version_id
session_folder
trajectory_file
trajectory_source_kind
run_started_at
run_finished_at
run_status
settings_hash
attempt_number
supersedes_idtracker_run_id
missing_coordinate_summary
error_log_path
slurm_job_id
created_at
notes
```

`run_status` examples:

```text
PENDING
RUNNING
COMPLETE
FAILED
SUPERSEDED
NEEDS_RERUN
EXCLUDED
```

### 7.5 `postprocessing_runs`

One row per post-processing attempt.

Suggested fields:

```text
postprocessing_run_id
tracking_target_id
idtracker_run_id
postprocessing_settings_hash
script_version
analysis_start_frame
analysis_end_frame_inclusive
window_frames
movement_threshold_px
jump_threshold_px
wall_buffer_px
fungus_buffer_px
social_distance_px
use_social_disappearance
output_csv_path
output_pdf_path
run_status
created_at
slurm_job_id
notes
```

`run_status` examples:

```text
PENDING
RUNNING
COMPLETE_REVIEW_NEEDED
FAILED
SUPERSEDED
RERUN_REQUESTED
QC_APPROVED
QC_REJECTED
```

### 7.6 `qc_decisions`

Append-only table. Every human decision creates a new row.

Suggested fields:

```text
qc_decision_id
tracking_target_id
postprocessing_run_id
idtracker_run_id
decision
decision_reason
reviewer
decided_at
review_pdf_path
missing_frames_percent
script_version
notes
```

`decision` examples:

```text
APPROVED
RERUN_IDTRACKER
RERUN_POSTPROCESSING
NEEDS_START_TIME
EXCLUDE_FROM_ANALYSIS
RETURN_TO_UNREVIEWED
```

Final analysis data is exported only from the latest current decision where:

```text
decision = APPROVED
```

### 7.7 `artifacts`

Optional but useful. One row per important file artifact.

Suggested fields:

```text
artifact_id
tracking_target_id
artifact_type
path
created_at
source_stage
hash
notes
```

Examples of `artifact_type`:

```text
video
still_png
toml_original
toml_registry_copy
toml_sidecar_json
idtracker_session_folder
trajectory_file
postprocessing_csv
postprocessing_pdf
approved_pdf_copy
```

## 8. Video Intake Workflow

### User-facing behavior

1. User selects or imports one or more Basler videos.
2. User labels each video as:
   - `BA`;
   - `fight`;
   - `other`.
3. System creates or updates a `videos` row.
4. System generates a PNG still at frame 2000.
5. GUI displays the still.
6. User identifies occupied cells.
7. System creates one `tracking_targets` row per selected cell.

### Still generation

Use `ffmpeg` to create a full-resolution PNG still.

Example:

```bash
ffmpeg -y -i input_video.mp4 -vf "select=eq(n\,2000)" -vframes 1 output_frame_2000.png
```

Record:

```text
still_frame_number
still_png_path
still_created_at
```

If frame 2000 does not exist, use an explicit fallback strategy:

1. try frame 1000;
2. try the first valid frame after the video starts;
3. if still unavailable, mark still generation failed and ask the user.

Record the actual frame used.

## 9. Cell Selection Workflow

Initial implementation should be simple:

- show the still PNG path or image;
- show a checklist of expected cells based on video type;
- user checks occupied cells.

Later implementation can add:

- clickable grid overlays;
- saved BA 20-cell layout;
- saved Fight 12-cell layout;
- ROI-position suggestions from existing TOMLs.

Minimum target metadata:

```text
video_id
cell_label
analysis_type
created_by
created_at
```

## 10. TOML Attachment Workflow

The existing segmentation app does not need to be modified.

Attach TOMLs outside the segmentation app.

### User workflow

1. User runs segmentation app normally.
2. User draws ROI, tunes thresholds/background/blob settings, and saves TOML.
3. Workflow manager imports one TOML or a folder of TOMLs.
4. System suggests target matches.
5. User confirms or corrects attachments.
6. System copies TOML into the registry folder.
7. System writes sidecar metadata JSON.
8. System writes or updates `toml_versions`.

### Matching priority

Safest first:

1. existing sidecar metadata with `tracking_target_id`;
2. exact video path inside TOML;
3. exact video filename inside TOML;
4. stable target token in filename;
5. cell label in filename;
6. ROI geometry compared to expected cell location;
7. manual attach.

Filename parsing is allowed only as fallback evidence, not as the source of
truth.

### Suggested TOML registry names

Stable compact form:

```text
target_20260701_camera2_b3_fight_ab12cd__toml_v001.toml
target_20260701_camera2_b3_fight_ab12cd__toml_v001.metadata.json
```

Human-readable form:

```text
Camera_2_40359705_20260701_1336_FIGHT_ACT1__B3__fight__target_ab12cd__toml_v001.toml
Camera_2_40359705_20260701_1336_FIGHT_ACT1__B3__fight__target_ab12cd__toml_v001.metadata.json
```

### Sidecar metadata JSON

Example:

```json
{
  "tracking_target_id": "target_20260701_camera2_b3_fight_ab12cd",
  "video_id": "video_20260701_camera2_act1",
  "video_filename": "Camera_2_40359705_20260701_1336_FIGHT_ACT1.mp4",
  "video_path": "/data/labs/vformic1-swat-lab/2026_Videos/...",
  "cell_label": "B3",
  "analysis_type": "fight",
  "toml_version": 1,
  "toml_hash": "sha256...",
  "created_at": "2026-07-25T...",
  "created_by": "vformic1-swat",
  "original_toml_path": "/original/path/file.toml"
}
```

If IDtracker tolerates extra TOML sections, optionally also embed:

```toml
[workflow_metadata]
tracking_target_id = "target_20260701_camera2_b3_fight_ab12cd"
video = "Camera_2_40359705_20260701_1336_FIGHT_ACT1.mp4"
cell_label = "B3"
analysis_type = "fight"
toml_version = 1
```

The sidecar JSON should still be authoritative.

## 11. Leave Room For Automated TOML Creation

Do not implement automated TOML generation in the first MVP, but design the
schema so it can be added later.

Future automated TOML creation might:

- use video-level stills and known cell layouts to propose ROI boxes;
- copy settings from a previous similar cell/video;
- generate draft TOMLs from templates;
- batch-create TOMLs for all selected occupied cells;
- compare generated ROI geometry to a manually corrected TOML;
- record whether a TOML was manual, templated, or auto-generated.

Add fields now that leave room for this:

In `toml_versions`:

```text
toml_creation_method
toml_template_id
toml_generated_by_script_version
toml_manual_review_status
toml_manual_reviewed_by
toml_manual_reviewed_at
```

Suggested values for `toml_creation_method`:

```text
manual_segmentation_app
manual_import_existing
template_generated
auto_generated_unreviewed
auto_generated_reviewed
```

Important rule for the future:

An auto-generated TOML should not be treated as ready for IDtracker unless it
has either passed explicit validation or been manually reviewed.

## 12. Backwards Compatibility Plan

The system must import existing data.

### Existing videos

Scan broad lab roots such as:

```text
/data/labs/vformic1-swat-lab/
```

but avoid unrelated users/labs and hidden/system folders.

Find:

- video files;
- TOMLs;
- `session.json`;
- trajectory files;
- `run_metadata.json`;
- post-processing CSVs/PDFs where available.

### Existing TOMLs

For old TOMLs:

1. parse video/cell from filename only as draft evidence;
2. parse video path from TOML if possible;
3. create draft tracking targets;
4. mark uncertain matches as `NEEDS_HUMAN_IDENTITY_REVIEW`;
5. let user confirm or correct in GUI;
6. once confirmed, write sidecar JSON and registry copy.

### Existing IDtracker sessions

For old session folders:

1. link via `run_metadata.json` if available;
2. else inspect `session.json`;
3. else inspect trajectory folder/session path;
4. if identity is incomplete, create an orphan record;
5. GUI lets user attach orphan session to a target.

Never guess silently.

## 13. Duplicate And Rerun Control

Before launching IDtracker, the GUI must check:

- Does target already have a complete IDtracker run?
- Does target already have an approved post-processing result?
- Does target already have a pending rerun request?
- Has the same TOML hash already been run?
- How many previous runs exist?
- Was the target excluded?

If risk exists, show a warning:

```text
This target already has 5 IDtracker runs and 1 approved post-processing result.
Launching another IDtracker run will create a new run history entry. Continue?
```

This prevents difficult videos from being rerun many times without visibility.

## 14. IDtracker Run Manager GUI

Purpose:

- launch IDtracker runs and reruns;
- track status;
- register session folders;
- avoid duplicate unknown runs.

Should show:

- video;
- cell;
- analysis type;
- current TOML version;
- number of IDtracker attempts;
- latest run status;
- missing frames summary if known;
- current target status.

Actions:

- run selected targets;
- rerun selected targets;
- mark target excluded;
- attach orphan session;
- open session folder;
- export needs-rerun report.

This GUI should not approve final biological data.

## 15. Post-processing GUI

Purpose:

- run post-processing on selected IDtracker runs;
- produce review artifacts;
- not write final data.

Should show:

- target;
- latest IDtracker run;
- trajectory source;
- start frame status;
- processing settings;
- post-processing status;
- output CSV/PDF paths.

Actions:

- run post-processing;
- run SLURM batch;
- import manual start times;
- run jump audit;
- rerun post-processing with changed settings;
- download review artifacts.

Outputs are review artifacts only.

## 16. QC Review GUI

Purpose:

- human review of post-processing PDFs;
- final approval or rerun/exclusion decisions.

Should include rapid-review behavior:

- `Start rapid review`;
- space opens selected PDF;
- `A` approves;
- `R` opens or uses rerun decision;
- after decision, next PDF opens automatically.

QC choices:

```text
APPROVED
RERUN_IDTRACKER
RERUN_POSTPROCESSING
NEEDS_START_TIME
EXCLUDE_FROM_ANALYSIS
RETURN_TO_UNREVIEWED
```

Suggested shortcut options:

Simple mode:

- `A` approve;
- `R` choose rerun reason/type in a small dialog;
- space open PDF.

Advanced mode:

- `A` approve;
- `I` rerun IDtracker;
- `P` rerun post-processing;
- `S` needs start time;
- `X` exclude;
- space open PDF.

QC writes decision rows. It should not delete raw outputs or session folders.

## 17. Final Data Export Rule

Final statistical data should be written only after QC.

Approved export query:

- latest QC decision is `APPROVED`;
- target is not superseded;
- post-processing run is the current approved run for that target;
- source files exist;
- schema version is compatible.

Export:

```text
approved_final_analysis.csv
```

Also export:

```text
approved_manifest.csv
approved_pdfs/
```

The final approved data export is the file downstream R should use.

## 18. Reports

Generate human-readable reports:

```text
tracking_targets_latest.csv
idtracker_runs_latest.csv
postprocessing_runs_latest.csv
qc_decisions_latest.csv
approved_final_analysis.csv
needs_idtracker_rerun.csv
needs_postprocessing_rerun.csv
needs_start_time.csv
excluded_from_analysis.csv
duplicates_audit.csv
orphan_sessions.csv
toml_identity_review_needed.csv
```

These are for humans, students, and R. SQLite remains the source of truth.

## 19. Provenance Requirements

Every important row should include:

```text
created_at
updated_at
created_by
script_version
source_path
hash where appropriate
notes
```

Never overwrite history.

If a TOML changes:

- create new TOML version;
- old version becomes superseded;
- target remains the same.

If IDtracker reruns:

- create new IDtracker run row;
- old run remains visible.

If post-processing reruns:

- create new post-processing run row;
- old output remains visible.

If QC decision changes:

- append new QC decision;
- old decision remains visible.

## 20. Scientific Guardrails

The system should make these distinctions explicit:

- IDtracker run complete does not mean biologically usable.
- Post-processing complete does not mean approved.
- Newest duplicate does not mean approved.
- Rerun needed does not mean exclude.
- Excluded does not mean deleted.
- Filename-derived identity is provisional until confirmed.
- Missing start time blocks final post-processing approval.
- Raw trajectory fallback must be reported.
- High missing-coordinate percentage should be prominent on QC PDFs.

## 21. Minimal Viable Product Sequence

Do not build everything at once.

### MVP 1: Registry And Still Intake

Build:

- SQLite schema;
- video import;
- ffmpeg still generation;
- simple GUI to label video type;
- simple GUI to select occupied cell labels;
- create tracking targets;
- export videos and targets CSVs.

Outputs:

- `videos`;
- `tracking_targets`;
- PNG stills.

### MVP 2: TOML Import And Attach

Build:

- TOML folder import;
- match suggestions;
- manual attach screen;
- registry TOML copy;
- sidecar metadata JSON;
- TOML version table.

Outputs:

- `toml_versions`;
- `tomls/active`;
- sidecar JSON.

### MVP 3: Existing Data Import

Build:

- scan existing Firebird roots;
- import old TOMLs;
- import old session folders;
- identify orphan sessions;
- identify uncertain target matches;
- duplicate audit.

Outputs:

- `orphan_sessions.csv`;
- `toml_identity_review_needed.csv`;
- draft registry rows.

### MVP 4: IDtracker Run Manager

Build:

- launch/rerun IDtracker using registered TOMLs;
- record session folders;
- prevent accidental duplicate reruns;
- track run status.

### MVP 5: Post-processing Integration

Migrate working behavior from `IDtracker_postprocessing_prototype`:

- SLURM processing;
- start-time handling;
- jump audit;
- PDF/CSV generation;
- automatic local download.

Attach every run to:

```text
tracking_target_id
idtracker_run_id
postprocessing_run_id
```

### MVP 6: QC Review

Migrate rapid review:

- cached PDFs;
- keyboard shortcuts;
- approve/rerun/exclude decisions;
- final approved export;
- approved PDF copy folder.

## 22. Suggested First Coding Prompt

Use this prompt to start implementation:

```text
Create a new repository called IDtracker_workflow_manager.

Build the first MVP only: a SQLite-backed workflow registry for IDtracker
videos and tracking targets.

Requirements:
1. Do not modify One_script_to_rule_them_all.
2. Do not modify the existing post-processing prototype except by reading code
   for reference.
3. Create a SQLite database schema with videos and tracking_targets tables.
4. Add a Python GUI that lets the user select/import Basler video files, choose
   video type (ba/fight/other), generate a PNG still at frame 2000 using ffmpeg,
   display the still path, and create tracking targets by selecting occupied
   cell labels.
5. Use stable generated IDs for video_id and tracking_target_id.
6. Store all records in SQLite.
7. Export human-readable CSVs for videos and tracking_targets.
8. Write a verbose README explaining the workflow, database schema, and why
   filename parsing is no longer authoritative.
9. Include tests for ID generation, duplicate target prevention, database
   writes, and CSV export.
10. Leave room in the schema for future automated TOML creation, but do not
    implement automated TOML generation in MVP 1.
11. Keep the design backwards compatible with existing TOMLs and IDtracker
    sessions, but do not implement TOML import yet.
```

## 23. Key Principle To Preserve

The workflow manager should make every stage auditable without making the fight
room workflow clunky.

The user should only need to identify:

- video;
- broad type: BA, fight, or other;
- occupied cells.

Everything else should be attachable later through the registry.

