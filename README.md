# IDtracker Workflow Manager

This repository is a planning and implementation home for a new SQLite-backed
workflow manager for Basler videos, IDtracker TOMLs, IDtracker runs,
post-processing runs, and human QC decisions.

The purpose is to stop treating filenames and scattered IDtracker session
folders as the source of truth. The central unit will be a stable
`tracking_target_id`: one intended video/cell/analysis target.

Initial implementation should start with the registry and still-frame intake
only. Existing post-processing and QC code should be borrowed carefully from
the standalone `IDtracker_postprocessing_prototype` after the registry model is
validated.

See:

- `planning/IDTRACKER_WORKFLOW_MANAGER_PLAN.md`

