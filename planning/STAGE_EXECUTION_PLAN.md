# IDtracker Workflow Manager Stage Execution Plan

Version: staged execution draft 2026-07-25

This file breaks the workflow-manager project into small implementation stages
that can be fed to Codex or another coding agent one at a time. The stages are
ordered to reduce risk: first build the registry and identity model, then add
TOML attachment, then import old data, then connect IDtracker, post-processing,
and QC.

Do not try to build all stages in one chat. Each stage should end with tests,
documentation, and a Git commit.

## Ground Rules For Every Stage

- Work only in:

```text
/Users/New/Library/CloudStorage/Dropbox/Projects/Coding_Repositories/IDtracker_workflow_manager
```

- Do not modify:

```text
/Users/New/Library/CloudStorage/Dropbox/Projects/One_script_to_rule_them_all
```

- Treat existing repos as read-only references unless explicitly instructed.
- Keep SQLite as the source of truth.
- CSVs are exports/reports, not the source of truth.
- Preserve all provenance. Never silently overwrite scientific history.
- Keep old-data compatibility in mind, but do not solve all legacy imports in
  Stage 1.
- For post-processing behavior, the authoritative implementation is the latest
  code in
  `/Users/New/Library/CloudStorage/Dropbox/Projects/Coding_Repositories/IDtracker_postprocessing_prototype`.
  Later stages should borrow, wrap, or migrate that code. Do not use older
  post-processing scripts from `One_script_to_rule_them_all`, temporary Codex
  folders, or earlier output directories except as historical context.
- Every stage should update README/planning docs if behavior changes.
- Every stage should add focused tests.
- Every stage should end with `git status`, tests, and a commit.

## Stage 0: Repository Bootstrap And Developer Notes

Goal: make the new repo easy to work in repeatedly.

Deliverables:

- Python package skeleton.
- Test runner.
- Basic README sections for setup and staged development.
- `planning/` files retained.
- Optional `AGENTS.md` with repo-specific constraints.

Suggested prompt:

```text
Work in /Users/New/Library/CloudStorage/Dropbox/Projects/Coding_Repositories/IDtracker_workflow_manager.

Implement Stage 0 only.

Create a Python package skeleton for the workflow manager, add a simple test
runner, and add repo-specific developer notes. Do not implement the database
schema yet except for placeholders if needed. Update README with setup and
staged-development instructions. Add focused smoke tests that prove the package
imports. Commit the result.
```

## Stage 1: SQLite Registry Core

Goal: create the stable database foundation.

Deliverables:

- SQLite schema for `videos` and `tracking_targets`.
- Database initialization code.
- Stable ID generation.
- Duplicate target prevention.
- CSV export for videos and tracking targets.
- Tests for schema creation, inserts, duplicate prevention, and export.

Important design rule:

`tracking_target_id` is the central unit. It represents one
video/cell/analysis target.

Suggested prompt:

```text
Work in /Users/New/Library/CloudStorage/Dropbox/Projects/Coding_Repositories/IDtracker_workflow_manager.

Implement Stage 1 only: the SQLite registry core.

Requirements:
1. Create database initialization code for videos and tracking_targets tables.
2. Use stable generated IDs for video_id and tracking_target_id.
3. Enforce uniqueness for video_path and for video_id + cell_label + analysis_type.
4. Add Python functions to upsert/import videos and create tracking targets.
5. Add CSV exports for videos and tracking_targets.
6. Add tests for database creation, duplicate target prevention, ID stability, and CSV export.
7. Update README and planning notes.
8. Do not build a GUI yet.
9. Do not implement TOML import yet.
10. Commit the result.
```

## Stage 2: Video Intake And Still Generation GUI

Goal: allow a user to register Basler videos and create PNG stills at frame
2000.

Deliverables:

- Python GUI for selecting/importing videos.
- Video type selector: BA, fight, other, unknown.
- `ffmpeg` still-frame generation.
- Store still metadata in SQLite.
- Export updated video table.
- Tests for ffmpeg command construction and fallback logic.

Suggested prompt:

```text
Work in /Users/New/Library/CloudStorage/Dropbox/Projects/Coding_Repositories/IDtracker_workflow_manager.

Implement Stage 2 only: video intake and still generation.

Requirements:
1. Add a Python GUI that lets the user select one or more video files.
2. Let the user label each video as ba, fight, other, or unknown.
3. Generate a PNG still at frame 2000 using ffmpeg at original resolution.
4. If frame 2000 is unavailable, use a documented fallback and record the actual frame used.
5. Store video and still metadata in SQLite.
6. Show the still path in the GUI; image display is useful but not required for the first pass.
7. Add tests for ffmpeg command construction, still path naming, and database updates.
8. Update README.
9. Commit the result.
```

## Stage 3: Occupied Cell Selection And Target Creation GUI

Goal: create tracking targets from a video-level still and user-selected cells.

Deliverables:

- GUI table/checklist for expected cells by video type.
- BA layout preset with possible 20 cells.
- Fight layout preset with possible 12 cells.
- User can select occupied cells.
- System creates tracking targets in SQLite.
- Duplicate creation is blocked with a clear message.

Suggested prompt:

```text
Work in /Users/New/Library/CloudStorage/Dropbox/Projects/Coding_Repositories/IDtracker_workflow_manager.

Implement Stage 3 only: occupied-cell selection and target creation.

Requirements:
1. In the GUI, allow the user to select a registered video and see its still path.
2. Provide cell checklists for ba, fight, and other/unknown.
3. For selected cells, create tracking_targets rows.
4. Prevent duplicate video/cell/analysis targets.
5. Show existing targets for the selected video.
6. Export tracking_targets_latest.csv.
7. Add tests for target creation and duplicate blocking.
8. Do not implement TOML import yet.
9. Commit the result.
```

## Stage 4: TOML Import And Manual Attach

Goal: attach segmentation-app TOMLs to known tracking targets without requiring
the segmentation app to know about the workflow manager.

Deliverables:

- TOML file/folder import.
- Match suggestions using safe evidence hierarchy.
- Manual attach screen.
- Registry copy of TOML.
- Sidecar metadata JSON.
- `toml_versions` table.
- Tests for TOML hashing, sidecar writing, version increments, and manual attach.

Suggested prompt:

```text
Work in /Users/New/Library/CloudStorage/Dropbox/Projects/Coding_Repositories/IDtracker_workflow_manager.

Implement Stage 4 only: TOML import and attach.

Requirements:
1. Add toml_versions table.
2. Import one TOML or a folder of TOMLs.
3. Suggest target matches using this priority: existing sidecar tracking_target_id, video path inside TOML, video filename inside TOML, target token in filename, cell label in filename, then manual attach.
4. Treat filename parsing as fallback evidence only.
5. Let the user manually attach a TOML to a target when confidence is low.
6. Copy attached TOMLs into the registry tomls/active folder.
7. Write sidecar metadata JSON with tracking_target_id, video, cell, analysis_type, toml_hash, original_toml_path, created/imported timestamps.
8. Store TOML version history in SQLite.
9. Leave room for future automated TOML creation fields, but do not implement automated TOML generation.
10. Add tests and update docs.
11. Commit the result.
```

## Stage 5: Existing Data Import And Orphan Discovery

Goal: bootstrap the registry from old videos, TOMLs, and session folders.

Deliverables:

- Read-only recursive scanner for Firebird roots.
- Discover videos, TOMLs, `run_metadata.json`, `session.json`, trajectories.
- Draft targets from old TOMLs.
- Orphan session report.
- Human identity review report.
- No silent guessing.

Suggested prompt:

```text
Work in /Users/New/Library/CloudStorage/Dropbox/Projects/Coding_Repositories/IDtracker_workflow_manager.

Implement Stage 5 only: existing data import and orphan discovery.

Requirements:
1. Add read-only scanning for user-provided Firebird roots.
2. Discover videos, TOMLs, run_metadata.json, session.json, and supported trajectory files.
3. Use existing metadata and sidecars when available.
4. Use filename parsing only as draft evidence.
5. Create draft targets only when identity is clear; otherwise write identity-review rows.
6. Add orphan session tracking for sessions that cannot be attached to a target.
7. Export orphan_sessions.csv and toml_identity_review_needed.csv.
8. Add tests using local fixture directories.
9. Do not launch IDtracker.
10. Commit the result.
```

## Stage 6: IDtracker Run Manager

Goal: launch and track IDtracker runs against registered targets and TOML
versions.

Deliverables:

- `idtracker_runs` table.
- Run/rerun GUI.
- Duplicate/rerun warnings.
- Session folder registration.
- Run status tracking.
- Rerun report.

Suggested prompt:

```text
Work in /Users/New/Library/CloudStorage/Dropbox/Projects/Coding_Repositories/IDtracker_workflow_manager.

Implement Stage 6 only: IDtracker run manager.

Requirements:
1. Add idtracker_runs table.
2. Add GUI actions to launch IDtracker for selected targets with current TOML versions.
3. Before launch, warn if the target already has complete runs, pending reruns, same TOML hash already run, exclusion, or approved post-processing.
4. Record session folders and run status.
5. Do not approve biological data in this GUI.
6. Export needs_idtracker_rerun.csv.
7. Add tests for duplicate-run warnings and run registration.
8. Commit the result.
```

## Stage 7: Post-processing Integration

Goal: attach post-processing attempts to IDtracker runs and produce review
artifacts.

Deliverables:

- `postprocessing_runs` table.
- Use selected `idtracker_run_id`.
- Integrate existing SLURM post-processing from the latest authoritative
  `IDtracker_postprocessing_prototype`.
- Produce CSV/PDF review artifacts.
- Store settings hash.
- Do not write final statistical data yet.

Suggested prompt:

```text
Work in /Users/New/Library/CloudStorage/Dropbox/Projects/Coding_Repositories/IDtracker_workflow_manager.

Implement Stage 7 only: post-processing integration.

Requirements:
1. Add postprocessing_runs table.
2. Borrow carefully from the latest authoritative IDtracker_postprocessing_prototype for SLURM processing, start handling, jump audit, PDF generation, automatic local download, rapid post-processing QC behavior, and approved/rerun report semantics.
3. Every post-processing run must link to tracking_target_id and idtracker_run_id.
4. Store settings and settings hash.
5. Outputs are review artifacts only, not final approved data.
6. Add tests for registry linking and output-record creation.
7. Commit the result.
```

## Stage 8: QC Review And Final Approved Export

Goal: approve only human-reviewed post-processing outputs and write final data.

Deliverables:

- `qc_decisions` table.
- Rapid PDF review GUI.
- Cached PDF opening.
- Approval/rerun/exclude decisions.
- Final approved CSV export.
- Approved PDF copy folder.

Suggested prompt:

```text
Work in /Users/New/Library/CloudStorage/Dropbox/Projects/Coding_Repositories/IDtracker_workflow_manager.

Implement Stage 8 only: QC review and final approved export.

Requirements:
1. Add append-only qc_decisions table.
2. Add rapid PDF review GUI: Start rapid review, space opens PDF, A approves, R chooses rerun type or reason, then next PDF opens.
3. QC choices must include APPROVED, RERUN_IDTRACKER, RERUN_POSTPROCESSING, NEEDS_START_TIME, EXCLUDE_FROM_ANALYSIS, RETURN_TO_UNREVIEWED.
4. Final statistical data is exported only from latest APPROVED decisions.
5. Export approved_final_analysis.csv, approved_manifest.csv, and approved_pdfs/.
6. Export needs_idtracker_rerun.csv, needs_postprocessing_rerun.csv, needs_start_time.csv, and excluded_from_analysis.csv.
7. Add tests for decision history and approved export selection.
8. Commit the result.
```

## Stage 9: Optional Future Automated TOML Creation

Do not implement this until the manual registry/TOML workflow is stable.

Possible later work:

- TOML templates by video type and cell layout.
- Draft ROI generation from known grid geometry.
- Copy settings from similar prior cells.
- Batch-create draft TOMLs for selected occupied cells.
- Require manual review before automated TOMLs are eligible for IDtracker.

Suggested future prompt:

```text
Work in /Users/New/Library/CloudStorage/Dropbox/Projects/Coding_Repositories/IDtracker_workflow_manager.

Design automated TOML creation as an optional assistant, not as the source of truth.

Requirements:
1. Use existing registered videos and tracking targets.
2. Generate draft TOMLs only from explicit templates or reviewed prior examples.
3. Mark generated TOMLs as auto_generated_unreviewed.
4. Do not allow IDtracker launch from an auto-generated TOML until it is manually reviewed or explicitly approved.
5. Preserve template provenance and script version.
6. Add tests and documentation.
```

## Recommended Chat Strategy

Use a new chat for implementation once ready.

Start with Stage 0 or Stage 1 only. Do not paste the whole long plan unless
needed. Instead, point Codex to:

```text
/Users/New/Library/CloudStorage/Dropbox/Projects/Coding_Repositories/IDtracker_workflow_manager/planning/IDTRACKER_WORKFLOW_MANAGER_PLAN.md
/Users/New/Library/CloudStorage/Dropbox/Projects/Coding_Repositories/IDtracker_workflow_manager/planning/STAGE_EXECUTION_PLAN.md
```

Then ask for one stage at a time.
