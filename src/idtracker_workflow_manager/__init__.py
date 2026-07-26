"""IDtracker workflow manager."""

from .registry import (
    DuplicateTrackingTargetError,
    create_tracking_target,
    export_tracking_targets_csv,
    export_videos_csv,
    generate_tracking_target_id,
    generate_video_id,
    initialize_database,
    record_still_failure,
    record_still_success,
    upsert_video,
)

__version__ = "0.2.0"

__all__ = [
    "DuplicateTrackingTargetError",
    "__version__",
    "create_tracking_target",
    "export_tracking_targets_csv",
    "export_videos_csv",
    "generate_tracking_target_id",
    "generate_video_id",
    "initialize_database",
    "record_still_failure",
    "record_still_success",
    "upsert_video",
]
