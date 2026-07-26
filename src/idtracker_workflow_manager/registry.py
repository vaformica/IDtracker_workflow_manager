"""SQLite registry core for videos and tracking targets."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import uuid


_ID_NAMESPACE = uuid.UUID("45639330-d34a-4c18-aea5-75c6f97f300d")
_VIDEO_TYPES = frozenset({"ba", "fight", "other", "unknown"})

VIDEO_EXPORT_COLUMNS = (
    "video_id",
    "video_path",
    "video_filename",
    "video_stem",
    "video_type",
    "video_type_source",
    "camera",
    "camera_id",
    "recording_date",
    "recording_time",
    "act",
    "year",
    "possible_cell_layout",
    "still_frame_number",
    "still_png_path",
    "still_created_at",
    "still_hash",
    "still_generation_status",
    "still_generation_error",
    "created_at",
    "updated_at",
    "created_by",
    "notes",
)

TRACKING_TARGET_EXPORT_COLUMNS = (
    "tracking_target_id",
    "video_id",
    "video_path",
    "video_filename",
    "cell_label",
    "analysis_type",
    "target_source",
    "target_status",
    "created_at",
    "created_by",
    "updated_at",
    "final_approved",
    "notes",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    video_id TEXT PRIMARY KEY,
    video_path TEXT NOT NULL UNIQUE,
    video_filename TEXT NOT NULL,
    video_stem TEXT NOT NULL,
    video_type TEXT NOT NULL
        CHECK (video_type IN ('ba', 'fight', 'other', 'unknown')),
    video_type_source TEXT NOT NULL,
    camera TEXT,
    camera_id TEXT,
    recording_date TEXT,
    recording_time TEXT,
    act TEXT,
    year INTEGER,
    possible_cell_layout TEXT,
    still_frame_number INTEGER,
    still_png_path TEXT,
    still_created_at TEXT,
    still_hash TEXT,
    still_generation_status TEXT NOT NULL DEFAULT 'NOT_ATTEMPTED',
    still_generation_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS tracking_targets (
    tracking_target_id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL,
    video_path TEXT NOT NULL,
    video_filename TEXT NOT NULL,
    cell_label TEXT NOT NULL,
    analysis_type TEXT NOT NULL,
    target_source TEXT NOT NULL,
    target_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    current_toml_version_id TEXT,
    current_idtracker_run_id TEXT,
    current_postprocessing_run_id TEXT,
    current_qc_decision_id TEXT,
    final_approved INTEGER NOT NULL DEFAULT 0
        CHECK (final_approved IN (0, 1)),
    notes TEXT,
    FOREIGN KEY (video_id) REFERENCES videos(video_id),
    UNIQUE (video_id, cell_label, analysis_type)
);
"""

_VIDEO_COLUMN_MIGRATIONS = {
    "still_hash": "TEXT",
    "still_generation_status": (
        "TEXT NOT NULL DEFAULT 'NOT_ATTEMPTED'"
    ),
    "still_generation_error": "TEXT",
}


class DuplicateTrackingTargetError(ValueError):
    """Raised when a video/cell/analysis target already exists."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalized_video_path(video_path: str | Path) -> str:
    path = Path(video_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return str(path.resolve(strict=False))


def _normalized_cell_label(cell_label: str) -> str:
    normalized = cell_label.strip().upper()
    if not normalized:
        raise ValueError("cell_label must not be empty")
    return normalized


def _normalized_analysis_type(analysis_type: str) -> str:
    normalized = analysis_type.strip().lower()
    if not normalized:
        raise ValueError("analysis_type must not be empty")
    return normalized


def generate_video_id(video_path: str | Path) -> str:
    """Return a deterministic ID for a normalized absolute video path."""

    normalized_path = _normalized_video_path(video_path)
    return f"video_{uuid.uuid5(_ID_NAMESPACE, normalized_path).hex}"


def generate_tracking_target_id(
    video_id: str, cell_label: str, analysis_type: str
) -> str:
    """Return a deterministic ID for one video/cell/analysis target."""

    normalized_video_id = video_id.strip()
    if not normalized_video_id:
        raise ValueError("video_id must not be empty")
    identity = "\x1f".join(
        (
            normalized_video_id,
            _normalized_cell_label(cell_label),
            _normalized_analysis_type(analysis_type),
        )
    )
    return f"target_{uuid.uuid5(_ID_NAMESPACE, identity).hex}"


def connect_database(database_path: str | Path) -> sqlite3.Connection:
    """Open a registry database with foreign keys and named rows enabled."""

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(database_path: str | Path) -> None:
    """Create the registry tables and apply additive column migrations."""

    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect_database(path) as connection:
        connection.executescript(_SCHEMA)
        existing_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(videos)")
        }
        for column_name, definition in _VIDEO_COLUMN_MIGRATIONS.items():
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE videos ADD COLUMN {column_name} {definition}"
                )


def upsert_video(
    database_path: str | Path,
    video_path: str | Path,
    *,
    video_type: str = "unknown",
    video_type_source: str = "manual",
    created_by: str,
    notes: str | None = None,
) -> sqlite3.Row:
    """Insert a video or update its mutable descriptive fields.

    The normalized path determines the stable ``video_id``. On an existing row,
    ``created_at`` and ``created_by`` are preserved.
    """

    normalized_path = _normalized_video_path(video_path)
    normalized_type = video_type.strip().lower()
    if normalized_type not in _VIDEO_TYPES:
        allowed = ", ".join(sorted(_VIDEO_TYPES))
        raise ValueError(f"video_type must be one of: {allowed}")
    if not video_type_source.strip():
        raise ValueError("video_type_source must not be empty")
    if not created_by.strip():
        raise ValueError("created_by must not be empty")

    path = Path(normalized_path)
    video_id = generate_video_id(normalized_path)
    timestamp = _utc_now()

    with connect_database(database_path) as connection:
        connection.execute(
            """
            INSERT INTO videos (
                video_id, video_path, video_filename, video_stem, video_type,
                video_type_source, created_at, updated_at, created_by, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(video_path) DO UPDATE SET
                video_filename = excluded.video_filename,
                video_stem = excluded.video_stem,
                video_type = excluded.video_type,
                video_type_source = excluded.video_type_source,
                updated_at = excluded.updated_at,
                notes = COALESCE(excluded.notes, videos.notes)
            """,
            (
                video_id,
                normalized_path,
                path.name,
                path.stem,
                normalized_type,
                video_type_source.strip(),
                timestamp,
                timestamp,
                created_by.strip(),
                notes,
            ),
        )
        row = connection.execute(
            "SELECT * FROM videos WHERE video_path = ?", (normalized_path,)
        ).fetchone()

    assert row is not None
    return row


def record_still_success(
    database_path: str | Path,
    video_id: str,
    *,
    frame_number: int,
    still_png_path: str | Path,
    still_hash: str | None = None,
) -> sqlite3.Row:
    """Record a successfully generated still for a registered video."""

    if frame_number < 0:
        raise ValueError("frame_number must be zero or greater")
    if still_hash is not None:
        normalized_hash = still_hash.strip().lower()
        if len(normalized_hash) != 64 or any(
            character not in "0123456789abcdef"
            for character in normalized_hash
        ):
            raise ValueError("still_hash must be a SHA-256 hex digest")
    else:
        normalized_hash = None
    normalized_path = _normalized_video_path(still_png_path)
    timestamp = _utc_now()

    with connect_database(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE videos
            SET still_frame_number = ?,
                still_png_path = ?,
                still_created_at = ?,
                still_hash = ?,
                still_generation_status = 'SUCCESS',
                still_generation_error = NULL,
                updated_at = ?
            WHERE video_id = ?
            """,
            (
                frame_number,
                normalized_path,
                timestamp,
                normalized_hash,
                timestamp,
                video_id,
            ),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"unknown video_id: {video_id}")
        row = connection.execute(
            "SELECT * FROM videos WHERE video_id = ?", (video_id,)
        ).fetchone()

    assert row is not None
    return row


def record_still_failure(
    database_path: str | Path,
    video_id: str,
    *,
    error_message: str,
) -> sqlite3.Row:
    """Record a failed still attempt without erasing an earlier good artifact."""

    message = error_message.strip()
    if not message:
        raise ValueError("error_message must not be empty")
    timestamp = _utc_now()

    with connect_database(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE videos
            SET still_generation_status = 'FAILED',
                still_generation_error = ?,
                updated_at = ?
            WHERE video_id = ?
            """,
            (message, timestamp, video_id),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"unknown video_id: {video_id}")
        row = connection.execute(
            "SELECT * FROM videos WHERE video_id = ?", (video_id,)
        ).fetchone()

    assert row is not None
    return row


def create_tracking_target(
    database_path: str | Path,
    video_id: str,
    cell_label: str,
    analysis_type: str,
    *,
    created_by: str,
    target_source: str = "manual_cell_selection",
    target_status: str = "TARGET_CREATED",
    notes: str | None = None,
) -> sqlite3.Row:
    """Create one target, rejecting duplicate video/cell/analysis identities."""

    normalized_cell = _normalized_cell_label(cell_label)
    normalized_analysis = _normalized_analysis_type(analysis_type)
    if not video_id.strip():
        raise ValueError("video_id must not be empty")
    if not created_by.strip():
        raise ValueError("created_by must not be empty")
    if not target_source.strip():
        raise ValueError("target_source must not be empty")
    if not target_status.strip():
        raise ValueError("target_status must not be empty")

    target_id = generate_tracking_target_id(
        video_id, normalized_cell, normalized_analysis
    )
    timestamp = _utc_now()

    with connect_database(database_path) as connection:
        video = connection.execute(
            "SELECT video_path, video_filename FROM videos WHERE video_id = ?",
            (video_id,),
        ).fetchone()
        if video is None:
            raise ValueError(f"unknown video_id: {video_id}")

        try:
            connection.execute(
                """
                INSERT INTO tracking_targets (
                    tracking_target_id, video_id, video_path, video_filename,
                    cell_label, analysis_type, target_source, target_status,
                    created_at, created_by, updated_at, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    target_id,
                    video_id,
                    video["video_path"],
                    video["video_filename"],
                    normalized_cell,
                    normalized_analysis,
                    target_source.strip(),
                    target_status.strip(),
                    timestamp,
                    created_by.strip(),
                    timestamp,
                    notes,
                ),
            )
        except sqlite3.IntegrityError as error:
            duplicate = connection.execute(
                """
                SELECT tracking_target_id
                FROM tracking_targets
                WHERE video_id = ? AND cell_label = ? AND analysis_type = ?
                """,
                (video_id, normalized_cell, normalized_analysis),
            ).fetchone()
            if duplicate is not None:
                raise DuplicateTrackingTargetError(
                    "tracking target already exists: "
                    f"{duplicate['tracking_target_id']}"
                ) from error
            raise

        row = connection.execute(
            "SELECT * FROM tracking_targets WHERE tracking_target_id = ?",
            (target_id,),
        ).fetchone()

    assert row is not None
    return row


def _export_query(
    database_path: str | Path,
    output_path: str | Path,
    *,
    query: str,
    columns: tuple[str, ...],
) -> Path:
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with connect_database(database_path) as connection:
        rows = connection.execute(query).fetchall()

    with destination.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(dict(row) for row in rows)

    return destination


def export_videos_csv(
    database_path: str | Path, output_path: str | Path
) -> Path:
    """Export a deterministic, human-readable videos CSV."""

    columns = ", ".join(VIDEO_EXPORT_COLUMNS)
    return _export_query(
        database_path,
        output_path,
        query=f"SELECT {columns} FROM videos ORDER BY video_path",
        columns=VIDEO_EXPORT_COLUMNS,
    )


def export_tracking_targets_csv(
    database_path: str | Path, output_path: str | Path
) -> Path:
    """Export a deterministic, human-readable tracking-targets CSV."""

    columns = ", ".join(TRACKING_TARGET_EXPORT_COLUMNS)
    return _export_query(
        database_path,
        output_path,
        query=(
            f"SELECT {columns} FROM tracking_targets "
            "ORDER BY video_path, cell_label, analysis_type"
        ),
        columns=TRACKING_TARGET_EXPORT_COLUMNS,
    )
