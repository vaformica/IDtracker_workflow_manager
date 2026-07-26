# IDtracker Workflow Manager Stage Execution Plan

Version: SSH/Firebird revision 2026-07-25

This file breaks the workflow-manager project into small implementation stages
that can be fed to Codex or another coding agent one at a time. The stages are
ordered to reduce risk: first build the registry and local prototype, then put
an SSH-only boundary around Firebird, build the installable Mac client, add
target creation, attach TOMLs, import old data, and finally connect IDtracker,
post-processing, and QC.

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
- The authoritative SQLite file and all authoritative workflow files live on
  Firebird and are opened only by Firebird-side code.
- Mac clients use SSH only. They must not require or use a mounted Firebird
  filesystem and must never open the SQLite file directly.
- Store canonical Firebird paths in the registry. Mac cache paths are
  disposable display paths, never scientific identity.
- Serialize Firebird-side database mutations and record the authenticated SSH
  username as provenance.
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

Implementation status: completed in Stage 1. The package now provides the two
registry tables, deterministic IDs, video upserts, duplicate-safe target
creation, full-table CSV exports, and focused tests. GUI, still, and TOML
behavior remain deferred to their later stages.

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

Implementation status: completed in Stage 2. The package now provides a
Tkinter multi-video intake GUI, per-row video types, full-resolution ffmpeg
still generation with frame 2000/1000/0 fallback, recorded success/failure
metadata, and an updated videos CSV export. This is a local prototype only. It
must not be used as the shared multi-user deployment because it opens SQLite
and video paths locally. Stage 3 introduces the SSH-only Firebird boundary.

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

## Stage 3: SSH Firebird Foundation

Goal: establish the safe remote boundary before any shared lab data are
registered.

Implementation status: completed in Stage 3 after verification and commit. The
package provides the versioned backend CLI, SSH transport, canonical-path
guards, serialized registry operations, hashed still metadata, verified
artifact caching, and auditable video/TOML discovery. Nothing is installed on
Firebird by this stage.

Architecture:

```text
Mac client
  -> SSH with the user's Firebird account
  -> versioned Firebird remote command
  -> authoritative SQLite and files on Firebird
```

Deliverables:

- Canonical Firebird-path normalization and stable IDs that never depend on a
  Mac path or mount point.
- Versioned JSON request/response protocol.
- Firebird-side command for health checks, allowed-root browsing, video
  registration, still generation/status, video listing, and exports.
- Configured video and TOML discovery roots for daily/Globus uploads.
- Remote scan/list actions that inventory new, changed, missing, and reappeared
  files without registering, attaching, or modifying them.
- Append-only discovery events plus scan summaries; ignore hidden, symlink,
  partial-transfer, and too-new files.
- Mac-side SSH command transport with timeouts and structured errors.
- Server-side ffmpeg execution.
- SHA-256 hashes for generated stills.
- Automatic SFTP/SCP still download into a disposable Mac cache, followed by
  hash verification.
- Authenticated SSH username provenance.
- Serialized Firebird-side database mutations.
- Reproducible Firebird backend installation bundle and a dry-run deployment
  check. Do not install it on Firebird without explicit user authorization.
- Deployment/configuration notes, including a required check that the chosen
  Firebird host/database directory safely supports the selected SQLite writer
  design.
- Tests with local fixtures and a fake SSH transport; no real Firebird writes.

Important boundaries:

- Do not build the cell-selection GUI yet.
- Do not mount Firebird.
- Do not download source videos to the Mac.
- Do not accept arbitrary remote filesystem roots from a client.
- Do not deploy to or mutate Firebird during automated tests.

Suggested prompt:

```text
Work in /Users/New/Library/CloudStorage/Dropbox/Projects/Coding_Repositories/IDtracker_workflow_manager.

Implement Stage 3 only: the SSH Firebird foundation.

Requirements:
1. Macs must use SSH only and must never mount Firebird or open SQLite directly.
2. Add a versioned JSON Firebird remote command and a Mac SSH transport.
3. Store and hash identities from canonical Firebird paths only.
4. Restrict remote browsing to configured lab video roots.
5. Add approved video/TOML discovery roots and remote scan/list actions for daily or Globus uploads.
6. Keep discovery separate from video registration, TOML attachment, and target creation.
7. Ignore hidden, symlink, partial-transfer, and configurable too-new files; record new/changed/missing events.
8. Run ffmpeg on Firebird, store stills there, and return metadata plus SHA-256.
9. Automatically download stills to a disposable Mac cache and verify hashes.
10. Derive mutation provenance from the authenticated Firebird user.
11. Serialize SQLite mutations through one tested writer mechanism.
12. Add local fixture/fake-SSH tests; do not touch real Firebird data.
13. Prepare a reproducible Firebird installation bundle and dry-run check, but
    do not install it remotely without explicit authorization.
14. Do not implement cell selection, target creation UI, or TOML import.
15. Update docs and commit the result.
```

## Stage 4: Installable Mac Remote Intake And Still Viewer

Goal: turn the remote foundation into an installable Mac application that can
browse Firebird videos and display downloaded stills.

Deliverables:

- Installable Mac `.app` build, with signing/notarization requirements
  documented; do not claim it is signed without the required Apple credentials.
- First-run SSH host/user/configuration screen.
- Connection and remote-version checks.
- Remote browser limited to allowed Firebird video roots.
- **Scan for new files** action and separate queues for unregistered videos and
  unattached TOMLs discovered after daily/Globus uploads.
- Multi-video selection and per-video `ba`, `fight`, `other`, or `unknown`
  labeling.
- Remote video registration and remote still-generation actions.
- Automatic verified still download and in-app image display.
- Cache refresh and clear actions that cannot delete Firebird artifacts.
- Clear offline, permission, ffmpeg, and protocol-mismatch errors.
- Tests for GUI-independent workflows, cache behavior, and installer build.

Suggested prompt:

```text
Work in /Users/New/Library/CloudStorage/Dropbox/Projects/Coding_Repositories/IDtracker_workflow_manager.

Implement Stage 4 only: the installable Mac remote intake and still viewer.

Requirements:
1. Build the Mac GUI on the Stage 3 SSH transport; never open Firebird paths locally.
2. Let users configure and test their Firebird SSH connection.
3. Browse only server-approved video roots.
4. Add Scan for new files and display separate unregistered-video and unattached-TOML queues.
5. Do not auto-register or auto-attach discoveries.
6. Register and label multiple remote videos.
7. Generate stills remotely, download them automatically, verify their hashes, and display them.
8. Treat the local cache as disposable and keep authoritative Firebird paths visible.
9. Produce an installable Mac application artifact and document installation.
10. Do not add occupied-cell selection or target creation yet.
11. Add tests and commit the result.
```

## Stage 5: Occupied Cell Selection And Remote Target Creation

Goal: create tracking targets from displayed cached stills while keeping every
authoritative mutation on Firebird.

Deliverables:

- In-app display of the verified cached still.
- BA layout preset with possible 20 cells.
- Fight layout preset with possible 12 cells.
- Checklist/manual labels for other or unknown layouts.
- Existing-target display for the selected remote video.
- Remote duplicate-safe target creation through SSH.
- Remote `tracking_targets_latest.csv` export.

Suggested prompt:

```text
Work in /Users/New/Library/CloudStorage/Dropbox/Projects/Coding_Repositories/IDtracker_workflow_manager.

Implement Stage 5 only: occupied-cell selection and remote target creation.

Requirements:
1. Display the hash-verified cached still while retaining its authoritative Firebird path.
2. Provide BA 20-cell and Fight 12-cell presets plus manual other/unknown labels.
3. Submit selected cells through SSH and create tracking targets on Firebird.
4. Never store Mac cache paths as video/still identity.
5. Prevent duplicates and show existing targets clearly.
6. Export tracking_targets_latest.csv on Firebird.
7. Add tests using fake SSH; do not touch real Firebird data.
8. Do not implement TOML import yet.
9. Commit the result.
```

## Stage 6: TOML Import And Manual Attach

Goal: attach segmentation-app TOMLs to known tracking targets without requiring
the segmentation app to know about the workflow manager.

Deliverables:

- Mac TOML file/folder upload through SSH and/or remote Firebird TOML browsing.
- Match suggestions using safe evidence hierarchy.
- Manual attach screen.
- Authoritative Firebird registry copy of TOML.
- Sidecar metadata JSON.
- `toml_versions` table.
- Tests for TOML hashing, sidecar writing, version increments, and manual attach.

Suggested prompt:

```text
Work in /Users/New/Library/CloudStorage/Dropbox/Projects/Coding_Repositories/IDtracker_workflow_manager.

Implement Stage 6 only: TOML import and attach.

Requirements:
1. Add toml_versions table.
2. Upload one Mac TOML or folder through SSH, or select TOMLs already on Firebird.
3. Suggest target matches using this priority: existing sidecar tracking_target_id, video path inside TOML, video filename inside TOML, target token in filename, cell label in filename, then manual attach.
4. Treat filename parsing as fallback evidence only.
5. Let the user manually attach a TOML to a target when confidence is low.
6. Perform attachment and copying on Firebird; never write SQLite from the Mac.
7. Write sidecar metadata JSON with tracking_target_id, video, cell, analysis_type, toml_hash, original_toml_path, created/imported timestamps.
8. Store TOML version history in SQLite.
9. Leave room for future automated TOML creation fields, but do not implement automated TOML generation.
10. Add tests and update docs.
11. Commit the result.
```

## Stage 7: Existing Data Import And Orphan Discovery

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

Implement Stage 7 only: existing data import and orphan discovery.

Requirements:
1. Execute read-only scanning on Firebird for administrator-approved roots.
2. Discover videos, TOMLs, run_metadata.json, session.json, and supported trajectory files.
3. Use existing metadata and sidecars when available.
4. Use filename parsing only as draft evidence.
5. Create draft targets only when identity is clear; otherwise write identity-review rows.
6. Add orphan session tracking for sessions that cannot be attached to a target.
7. Export orphan_sessions.csv and toml_identity_review_needed.csv.
8. Add tests using local fixture directories and fake SSH.
9. Do not launch IDtracker.
10. Commit the result.
```

## Stage 8: IDtracker Run Manager

Goal: launch and track IDtracker runs against registered targets and TOML
versions.

Deliverables:

- `idtracker_runs` table.
- Mac run/rerun GUI backed by remote Firebird actions.
- Duplicate/rerun warnings.
- Session folder registration.
- Run status tracking.
- Rerun report.

Suggested prompt:

```text
Work in /Users/New/Library/CloudStorage/Dropbox/Projects/Coding_Repositories/IDtracker_workflow_manager.

Implement Stage 8 only: IDtracker run manager.

Requirements:
1. Add idtracker_runs table.
2. Add Mac GUI actions that request Firebird-side IDtracker launch for selected targets with current TOML versions.
3. Before launch, warn if the target already has complete runs, pending reruns, same TOML hash already run, exclusion, or approved post-processing.
4. Record session folders and run status.
5. Do not approve biological data in this GUI.
6. Export needs_idtracker_rerun.csv.
7. Add tests for duplicate-run warnings, remote launch requests, and run registration.
8. Commit the result.
```

## Stage 9: Post-processing Integration

Goal: attach post-processing attempts to IDtracker runs and produce review
artifacts.

Deliverables:

- `postprocessing_runs` table.
- Use selected `idtracker_run_id`.
- Integrate existing SLURM post-processing from the latest authoritative
  `IDtracker_postprocessing_prototype`.
- Produce CSV/PDF review artifacts.
- Download only requested review artifacts to a verified disposable Mac cache.
- Store settings hash.
- Do not write final statistical data yet.

Suggested prompt:

```text
Work in /Users/New/Library/CloudStorage/Dropbox/Projects/Coding_Repositories/IDtracker_workflow_manager.

Implement Stage 9 only: post-processing integration.

Requirements:
1. Add postprocessing_runs table.
2. Borrow carefully from the latest authoritative IDtracker_postprocessing_prototype for SLURM processing, start handling, jump audit, PDF generation, verified local-cache download, rapid post-processing QC behavior, and approved/rerun report semantics.
3. Every post-processing run must link to tracking_target_id and idtracker_run_id.
4. Store settings and settings hash.
5. Outputs are review artifacts only, not final approved data.
6. Add tests for registry linking and output-record creation.
7. Commit the result.
```

## Stage 10: QC Review, New Review Rounds, And Final Approved Export

Goal: approve only human-reviewed post-processing outputs and write final data.

Deliverables:

- `review_rounds` table.
- `qc_decisions` table.
- Explicit review rounds that allow every eligible imported session, including
  previously approved or rejected sessions, to receive a completely new human
  review without erasing earlier decisions.
- Mac rapid PDF review GUI using SSH-backed decisions.
- Hash-verified cached PDF opening.
- Approval/rerun/exclude decisions.
- Final approved CSV export.
- Approved PDF copy folder.

Suggested prompt:

```text
Work in /Users/New/Library/CloudStorage/Dropbox/Projects/Coding_Repositories/IDtracker_workflow_manager.

Implement Stage 10 only: QC review rounds and final approved export.

Requirements:
1. Add review_rounds and append-only qc_decisions tables.
2. Let the user start a completely new review round containing every eligible imported session, including sessions approved, rejected, or excluded previously.
3. Preserve all earlier decisions and identify every decision by review_round_id.
4. Add rapid PDF review GUI: Start rapid review, space opens PDF, A approves, R chooses rerun type or reason, then next PDF opens.
5. QC choices must include APPROVED, RERUN_IDTRACKER, RERUN_POSTPROCESSING, NEEDS_START_TIME, EXCLUDE_FROM_ANALYSIS, RETURN_TO_UNREVIEWED.
6. Final statistical data is exported only from the explicitly selected completed review round and its latest APPROVED decisions.
7. Export approved_final_analysis.csv, approved_manifest.csv, and approved_pdfs/.
8. Export needs_idtracker_rerun.csv, needs_postprocessing_rerun.csv, needs_start_time.csv, and excluded_from_analysis.csv.
9. Add tests for review-round scope, decision history, and approved export selection.
10. Commit the result.
```

## Stage 11: Optional Future Automated TOML Creation

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

Stages 0 through 2 are complete. The next implementation request should be
Stage 3. Point Codex to:

```text
/Users/New/Library/CloudStorage/Dropbox/Projects/Coding_Repositories/IDtracker_workflow_manager/planning/IDTRACKER_WORKFLOW_MANAGER_PLAN.md
/Users/New/Library/CloudStorage/Dropbox/Projects/Coding_Repositories/IDtracker_workflow_manager/planning/STAGE_EXECUTION_PLAN.md
```

Then ask for one stage at a time.
