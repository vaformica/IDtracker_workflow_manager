# IDtracker Workflow Manager Implementation Plan

Version: SSH/Firebird architecture revision 2026-07-25

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
  firebird_remote/
  ssh_client/
  mac_app/
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

The deployed system uses an SSH-only client/server boundary:

```text
Installable Mac GUI
  -> SSH using the user's Firebird account
  -> Firebird remote command/backend
  -> authoritative SQLite registry and files on Firebird
```

Mac clients must not mount Firebird and must not open the SQLite file directly.
All authoritative reads, writes, video access, ffmpeg execution, target
creation, and later workflow actions happen on Firebird. The Mac app receives
structured results and downloads only review/display artifacts into a local
cache.

The Stage 2 local GUI is a tested prototype of intake and still behavior. It is
not the intended multi-user deployment architecture and must be refactored
behind this SSH boundary before real shared data are registered.

## 2.1 Authoritative Post-processing Implementation

For post-processing behavior, the current best implementation is the latest
standalone code in:

```text
/Users/New/Library/CloudStorage/Dropbox/Projects/Coding_Repositories/IDtracker_postprocessing_prototype
```

That repo's current `processor.py`, `firebird_gui.py`, `combine_results.py`,
`slurm_worker.py`, `slurm_finalize.py`, `postprocessing_qc.py`, tests, README,
METHODS, and DATA_DICTIONARY are the authoritative reference for:

- trajectory-source priority;
- raw fallback warnings;
- analysis-window calculations;
- one-frame jump handling;
- social disappearance substitution;
- wall/fungus geometry;
- post-wake and fixed 3600-frame summaries;
- PDF generation;
- SLURM execution;
- automatic downloads;
- rapid post-processing QC review;
- approved/rerun report generation.

Do not use older post-processing scripts from `One_script_to_rule_them_all`,
temporary Codex folders, or earlier output directories as implementation
sources. Those older scripts can be inspected only as historical context or as
examples of problems the new system is designed to avoid.

The workflow manager may eventually absorb, vendor, or wrap the latest
standalone post-processing prototype. Until that migration is explicitly
implemented, tested, and documented, the latest standalone prototype remains the
scientifically preferred post-processing code.

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
- no separate database server required for the initial Firebird backend;
- runs through Python on Firebird;
- easy backup;
- Python support through `sqlite3`;
- R support through `DBI` and `RSQLite`;
- can export clean CSVs for students and R;
- can enforce uniqueness and foreign-key relationships.

The SQLite file lives on Firebird and is opened only by Firebird-side code.
Mac clients never open it through a network mount. Firebird-side writes must be
serialized through one controlled writer/service or another tested
single-writer mechanism. Before deployment, confirm that the chosen Firebird
host and database directory provide reliable SQLite locking; if they do not,
retain the same registry API but use a managed client/server database rather
than risking SQLite corruption.

All video identities use canonical Firebird paths, for example:

```text
/data/labs/vformic1-swat-lab/2026_Videos/example.mp4
```

Never derive `video_id` from a Mac path, downloaded cache path, username, or
machine-specific mount path.

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
Basler video already on Firebird
  -> remote ffmpeg still PNG on Firebird
  -> automatic verified download to Mac cache
  -> user-selected occupied cells in Mac GUI
  -> remote tracking-target creation on Firebird
  -> TOML versions
  -> IDtracker runs
  -> post-processing runs
  -> QC decisions
  -> approved final data
```

The user should not need to enter beetle biological IDs in the fight room.
During intake, the minimum metadata is:

- canonical Firebird video path;
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

Mac clients keep only a disposable local cache, suggested location:

```text
~/Library/Caches/IDtrackerWorkflowManager/
  stills/
  pdfs/
```

Every downloaded artifact must be accompanied by its authoritative Firebird
path and hash. The client verifies the hash after download and refreshes the
cache when the remote hash changes. Cache files are never the source of truth
and can be deleted and downloaded again.

## 6.1 SSH Transport And Remote Commands

Use the user's existing SSH identity and configured Firebird host. Do not
require a mounted filesystem.

The Mac client should invoke a versioned Firebird-side command and exchange
machine-readable JSON. Remote operations include:

- health/version check;
- list allowed video roots and directories;
- scan approved video and TOML inbox roots for new/changed files;
- list unregistered-video and unattached-TOML discoveries;
- register a canonical Firebird video path;
- generate or retrieve still metadata;
- download a still through SFTP/SCP;
- list videos and existing targets;
- create targets;
- export reports.

The Firebird backend must:

- restrict file browsing to configured lab roots;
- reject path traversal and paths outside those roots;
- obtain the authenticated remote username for provenance rather than trusting
  an arbitrary `created_by` string from the client;
- return stable error codes and JSON messages;
- log mutating requests;
- serialize database mutations;
- never stream whole videos to the Mac merely to make a still.

The SSH protocol and remote command version must be checked at connection time
so an old Mac app cannot silently write with an incompatible schema.

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
still_hash
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

### 7.3 Discovery Inventory

Folder scanning is inventory only. It never registers a video, attaches a TOML,
creates a tracking target, or modifies a discovered source file.

`discovery_scans` records every completed scan:

```text
scan_id
started_at
completed_at
authenticated_user
roots_json
scan_status
files_seen
discovered_count
changed_count
missing_count
unstable_count
issue_count
ignored_count
```

`file_discoveries` stores the current discoverability state:

```text
discovery_id
canonical_path
file_kind
size_bytes
mtime_ns
content_hash
discovery_status
availability_status
first_discovered_at
last_seen_at
registered_video_id
```

`discovery_events` is append-only and records `DISCOVERED`, `CHANGED`,
`MISSING`, and `REAPPEARED` events. TOMLs receive SHA-256 hashes. Large videos
use path, size, and modification-time evidence during discovery and are not
silently content-hashed in full.

`discovery_scan_issues` records the canonical path, reason, details, and scan
for hidden files, symlinks, partial-transfer names, too-new/changing files,
unsafe paths, stat failures, and directory-scan failures.

Ignore hidden files, symlinks, known partial-transfer suffixes, and files newer
than a configured minimum age. This prevents an in-progress Globus transfer
from being treated as ready. These files remain explicit scan issues rather
than disappearing silently. Missing and changed files remain explicit review
conditions.

### 7.4 `toml_versions`

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

### 7.5 `idtracker_runs`

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

### 7.6 `postprocessing_runs`

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

### 7.7 `review_rounds`

One row per explicit human-review campaign.

Suggested fields:

```text
review_round_id
review_round_label
scope_definition_json
include_prior_approved
include_prior_rejected
include_prior_excluded
created_at
created_by
started_at
completed_at
review_round_status
notes
```

The scope is frozen when a review round starts. A new comprehensive review can
include every eligible imported session without changing any earlier review
round or QC decision.

### 7.8 `qc_decisions`

Append-only table. Every human decision creates a new row.

Suggested fields:

```text
qc_decision_id
review_round_id
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

Final analysis data is exported only from the explicitly selected completed
review round and the latest decision within that round where:

```text
decision = APPROVED
```

### 7.9 `artifacts`

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

1. Mac app connects to Firebird through SSH.
2. User browses allowed Firebird directories and selects one or more Basler
   videos by canonical Firebird path.
3. User labels each video as:
   - `BA`;
   - `fight`;
   - `other`.
4. Firebird backend creates or updates a `videos` row.
5. Firebird runs ffmpeg and stores the PNG still in the registry.
6. Mac app automatically downloads the still to its local cache, verifies its
   hash, and displays it.
7. User identifies occupied cells.
8. Mac app submits the selected cells through SSH.
9. Firebird creates one `tracking_targets` row per selected cell.

### Still generation

Run `ffmpeg` on Firebird to create a full-resolution PNG still. The Mac must not
download the source video or require a local ffmpeg installation.

Example:

```bash
ffmpeg -y -i input_video.mp4 -vf "select=eq(n\,2000)" -vframes 1 output_frame_2000.png
```

Record:

```text
still_frame_number
still_png_path
still_created_at
still_hash
```

If frame 2000 does not exist, use an explicit fallback strategy:

1. try frame 1000;
2. try the first valid frame after the video starts;
3. if still unavailable, mark still generation failed and ask the user.

Record the actual frame used.

## 9. Cell Selection Workflow

Initial implementation should be simple:

- automatically download, hash-verify, and display the cached still image;
- retain the authoritative Firebird still path in metadata;
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

Target creation is a remote Firebird mutation. The Mac cache path must never be
stored as `video_path` or `still_png_path` in the authoritative registry.

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
- support explicit review rounds, including a completely new review of every
  eligible imported session regardless of its earlier approval/rejection.

Every review round has a stable ID, label, creator, creation time, scope, and
status. Starting a new review round must not erase or reinterpret prior
decisions. The GUI can deliberately include sessions approved, rejected, or
excluded in earlier systems so the lab can perform a new comprehensive
approval.

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

- review round is explicitly selected and complete;
- latest QC decision within that review round is `APPROVED`;
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
review_rounds.csv
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

### MVP 1: Registry Core And Local Prototype

Build:

- SQLite schema;
- deterministic registry identities;
- local ffmpeg still-generation prototype;
- local prototype GUI to label video type;
- tests for registry and fallback behavior.

Outputs:

- `videos`;
- `tracking_targets` schema and APIs;
- local prototype PNG stills.

This prototype is complete but is not the shared deployment model.

### MVP 2: SSH Firebird Foundation

Build:

- canonical Firebird path identity;
- versioned JSON remote commands;
- SSH client transport;
- Firebird-side registry ownership;
- serialized remote mutations;
- remote video browsing within allowed roots;
- server-side ffmpeg;
- still hashing and verified Mac download/cache.

Outputs:

- authoritative Firebird registry;
- remote still PNGs;
- disposable verified Mac still cache.

### MVP 3: Installable Mac Intake And Target GUI

Build:

- installable Mac application;
- SSH connection/settings screen;
- remote video browser;
- video-type labeling;
- automatic still download and display;
- occupied-cell presets;
- remote duplicate-safe target creation.

Outputs:

- `videos`;
- `tracking_targets`;
- `tracking_targets_latest.csv`.

### MVP 4: TOML Import And Attach

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

### MVP 5: Existing Data Import

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

### MVP 6: IDtracker Run Manager

Build:

- launch/rerun IDtracker using registered TOMLs;
- record session folders;
- prevent accidental duplicate reruns;
- track run status.

### MVP 7: Post-processing Integration

Migrate or wrap the latest working behavior from the authoritative
`IDtracker_postprocessing_prototype` repo:

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

### MVP 8: QC Review

Migrate rapid review:

- cached PDFs;
- explicit review rounds, including a new review of all eligible sessions;
- keyboard shortcuts;
- approve/rerun/exclude decisions;
- final approved export;
- approved PDF copy folder.

## 22. Suggested Next Coding Prompt

Stages 0 through 2 are complete as local/bootstrap work. Use this prompt for the
next architecture stage:

```text
Work in the IDtracker_workflow_manager repository.

Implement Stage 3 only: the SSH Firebird foundation.

The Macs must not mount Firebird or open SQLite directly. Add a versioned JSON
remote command interface, an SSH client transport, canonical Firebird-path
identity, allowed-root browsing, server-side ffmpeg, still hashing, automatic
verified still download to a disposable Mac cache, authenticated-user
provenance, and serialized database writes. Keep target-selection UI for Stage
5. Use local fixtures/fake SSH for tests and do not write real Firebird data.
```

## 23. Key Principle To Preserve

The workflow manager should make every stage auditable without making the fight
room workflow clunky.

The user should only need to identify:

- video;
- broad type: BA, fight, or other;
- occupied cells.

Everything else should be attachable later through the registry.
