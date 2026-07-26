"""Auditable discovery of new or changed Firebird video and TOML files."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Any, Callable
import uuid

from .firebird_config import FirebirdBackendConfig
from .registry import connect_database


_DISCOVERY_NAMESPACE = uuid.UUID("9f5b73f2-eb74-48c5-b713-fab848ed6428")
_IGNORED_SUFFIXES = frozenset(
    {".crdownload", ".download", ".part", ".partial", ".temp", ".tmp"}
)

_DISCOVERY_SCHEMA = """
CREATE TABLE IF NOT EXISTS discovery_scans (
    scan_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    authenticated_user TEXT NOT NULL,
    roots_json TEXT NOT NULL,
    scan_status TEXT NOT NULL,
    files_seen INTEGER NOT NULL,
    discovered_count INTEGER NOT NULL,
    changed_count INTEGER NOT NULL,
    missing_count INTEGER NOT NULL,
    unstable_count INTEGER NOT NULL,
    issue_count INTEGER NOT NULL,
    ignored_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS file_discoveries (
    discovery_id TEXT PRIMARY KEY,
    canonical_path TEXT NOT NULL UNIQUE,
    file_kind TEXT NOT NULL CHECK (file_kind IN ('video', 'toml')),
    size_bytes INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    content_hash TEXT,
    discovery_status TEXT NOT NULL,
    availability_status TEXT NOT NULL,
    first_discovered_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    registered_video_id TEXT,
    FOREIGN KEY (registered_video_id) REFERENCES videos(video_id)
);

CREATE TABLE IF NOT EXISTS discovery_events (
    event_id TEXT PRIMARY KEY,
    scan_id TEXT NOT NULL,
    discovery_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    size_bytes INTEGER,
    mtime_ns INTEGER,
    content_hash TEXT,
    FOREIGN KEY (scan_id) REFERENCES discovery_scans(scan_id),
    FOREIGN KEY (discovery_id) REFERENCES file_discoveries(discovery_id)
);

CREATE TABLE IF NOT EXISTS discovery_scan_issues (
    issue_id TEXT PRIMARY KEY,
    scan_id TEXT NOT NULL,
    canonical_path TEXT,
    issue_reason TEXT NOT NULL,
    issue_detail TEXT,
    observed_at TEXT NOT NULL,
    FOREIGN KEY (scan_id) REFERENCES discovery_scans(scan_id)
);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def initialize_discovery_schema(database_path: str | Path) -> None:
    """Create Stage 3 scan inventory and append-only event tables."""

    with connect_database(database_path) as connection:
        connection.executescript(_DISCOVERY_SCHEMA)
        existing_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(discovery_scans)"
            )
        }
        for column_name in ("unstable_count", "issue_count"):
            if column_name not in existing_columns:
                connection.execute(
                    f"ALTER TABLE discovery_scans "
                    f"ADD COLUMN {column_name} INTEGER NOT NULL DEFAULT 0"
                )


def _discovery_id(path: Path) -> str:
    return f"discovery_{uuid.uuid5(_DISCOVERY_NAMESPACE, str(path)).hex}"


def _hash_small_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _classify(path: Path, config: FirebirdBackendConfig) -> str | None:
    suffix = path.suffix.lower()
    if suffix in config.video_extensions and _inside_any(
        path, config.video_roots
    ):
        return "video"
    if suffix == ".toml" and _inside_any(path, config.toml_roots):
        return "toml"
    return None


def _inside_any(path: Path, roots: tuple[Path, ...]) -> bool:
    return any(path.is_relative_to(root) for root in roots)


def _insert_event(
    connection: sqlite3.Connection,
    *,
    scan_id: str,
    discovery_id: str,
    event_type: str,
    observed_at: str,
    size_bytes: int | None,
    mtime_ns: int | None,
    content_hash: str | None,
) -> None:
    connection.execute(
        """
        INSERT INTO discovery_events (
            event_id, scan_id, discovery_id, event_type, observed_at,
            size_bytes, mtime_ns, content_hash
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"event_{uuid.uuid4().hex}",
            scan_id,
            discovery_id,
            event_type,
            observed_at,
            size_bytes,
            mtime_ns,
            content_hash,
        ),
    )


def _insert_issue(
    connection: sqlite3.Connection,
    *,
    scan_id: str,
    canonical_path: str | None,
    issue_reason: str,
    issue_detail: str | None,
    observed_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO discovery_scan_issues (
            issue_id, scan_id, canonical_path, issue_reason, issue_detail,
            observed_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            f"issue_{uuid.uuid4().hex}",
            scan_id,
            canonical_path,
            issue_reason,
            issue_detail,
            observed_at,
        ),
    )


def scan_discovery_roots(
    database_path: str | Path,
    config: FirebirdBackendConfig,
    *,
    authenticated_user: str,
    now_provider: Callable[[], float] = time.time,
) -> dict[str, Any]:
    """Scan approved roots without registering or attaching discovered files."""

    if not authenticated_user.strip():
        raise ValueError("authenticated_user must not be empty")
    for root in config.discovery_roots:
        if not root.is_dir():
            raise ValueError(f"configured discovery root is unavailable: {root}")

    initialize_discovery_schema(database_path)
    scan_id = f"scan_{uuid.uuid4().hex}"
    started_at = _utc_now()
    observed_at = started_at
    now_seconds = now_provider()
    seen_paths: set[str] = set()
    files_seen = 0
    discovered_count = 0
    changed_count = 0
    unstable_count = 0
    issue_count = 0
    ignored_count = 0

    with connect_database(database_path) as connection:
        connection.execute(
            """
            INSERT INTO discovery_scans (
                scan_id, started_at, completed_at, authenticated_user,
                roots_json, scan_status, files_seen, discovered_count,
                changed_count, missing_count, unstable_count, issue_count,
                ignored_count
            )
            VALUES (?, ?, ?, ?, ?, 'RUNNING', 0, 0, 0, 0, 0, 0, 0)
            """,
            (
                scan_id,
                started_at,
                started_at,
                authenticated_user.strip(),
                json.dumps(
                    [str(root) for root in config.discovery_roots],
                    sort_keys=True,
                ),
            ),
        )

        for root in config.discovery_roots:
            walk_errors: list[OSError] = []
            for directory_path, directory_names, file_names in os.walk(
                root,
                followlinks=False,
                onerror=walk_errors.append,
            ):
                directory = Path(directory_path)
                retained_directories: list[str] = []
                for name in directory_names:
                    child = directory / name
                    if name.startswith(".") or child.is_symlink():
                        ignored_count += 1
                        continue
                    canonical_child = child.resolve(strict=False)
                    if canonical_child == config.registry_root or (
                        canonical_child.is_relative_to(config.registry_root)
                    ):
                        ignored_count += 1
                        continue
                    retained_directories.append(name)
                directory_names[:] = retained_directories

                for name in file_names:
                    candidate = directory / name
                    if name.startswith("."):
                        ignored_count += 1
                        issue_count += 1
                        _insert_issue(
                            connection,
                            scan_id=scan_id,
                            canonical_path=str(candidate.resolve(strict=False)),
                            issue_reason="HIDDEN_FILE_SKIPPED",
                            issue_detail=None,
                            observed_at=observed_at,
                        )
                        continue
                    if candidate.is_symlink():
                        ignored_count += 1
                        issue_count += 1
                        _insert_issue(
                            connection,
                            scan_id=scan_id,
                            canonical_path=str(candidate.resolve(strict=False)),
                            issue_reason="SYMLINK_SKIPPED",
                            issue_detail=None,
                            observed_at=observed_at,
                        )
                        continue
                    if candidate.suffix.lower() in _IGNORED_SUFFIXES:
                        ignored_count += 1
                        issue_count += 1
                        _insert_issue(
                            connection,
                            scan_id=scan_id,
                            canonical_path=str(candidate.resolve(strict=False)),
                            issue_reason="PARTIAL_TRANSFER_NAME",
                            issue_detail=None,
                            observed_at=observed_at,
                        )
                        continue
                    canonical_path = candidate.resolve(strict=False)
                    if not _inside_any(
                        canonical_path, config.discovery_roots
                    ) or canonical_path.is_relative_to(config.registry_root):
                        ignored_count += 1
                        issue_count += 1
                        _insert_issue(
                            connection,
                            scan_id=scan_id,
                            canonical_path=str(canonical_path),
                            issue_reason="OUTSIDE_ROOT_OR_REGISTRY_SKIPPED",
                            issue_detail=None,
                            observed_at=observed_at,
                        )
                        continue
                    file_kind = _classify(canonical_path, config)
                    if file_kind is None:
                        continue
                    try:
                        stat = canonical_path.stat()
                    except OSError as error:
                        ignored_count += 1
                        issue_count += 1
                        _insert_issue(
                            connection,
                            scan_id=scan_id,
                            canonical_path=str(canonical_path),
                            issue_reason="FILE_STAT_FAILED",
                            issue_detail=str(error),
                            observed_at=observed_at,
                        )
                        continue
                    seen_paths.add(str(canonical_path))
                    if (
                        now_seconds - stat.st_mtime
                        < config.minimum_file_age_seconds
                    ):
                        ignored_count += 1
                        unstable_count += 1
                        issue_count += 1
                        _insert_issue(
                            connection,
                            scan_id=scan_id,
                            canonical_path=str(canonical_path),
                            issue_reason="TOO_NEW_OR_CHANGING",
                            issue_detail=(
                                "file age is below "
                                f"{config.minimum_file_age_seconds} seconds"
                            ),
                            observed_at=observed_at,
                        )
                        continue

                    files_seen += 1
                    content_hash = (
                        _hash_small_file(canonical_path)
                        if file_kind == "toml"
                        else None
                    )
                    existing = connection.execute(
                        """
                        SELECT * FROM file_discoveries
                        WHERE canonical_path = ?
                        """,
                        (str(canonical_path),),
                    ).fetchone()
                    if existing is None:
                        discovery_id = _discovery_id(canonical_path)
                        connection.execute(
                            """
                            INSERT INTO file_discoveries (
                                discovery_id, canonical_path, file_kind,
                                size_bytes, mtime_ns, content_hash,
                                discovery_status, availability_status,
                                first_discovered_at, last_seen_at
                            )
                            VALUES (?, ?, ?, ?, ?, ?, 'DISCOVERED', 'PRESENT',
                                    ?, ?)
                            """,
                            (
                                discovery_id,
                                str(canonical_path),
                                file_kind,
                                stat.st_size,
                                stat.st_mtime_ns,
                                content_hash,
                                observed_at,
                                observed_at,
                            ),
                        )
                        _insert_event(
                            connection,
                            scan_id=scan_id,
                            discovery_id=discovery_id,
                            event_type="DISCOVERED",
                            observed_at=observed_at,
                            size_bytes=stat.st_size,
                            mtime_ns=stat.st_mtime_ns,
                            content_hash=content_hash,
                        )
                        discovered_count += 1
                        continue

                    changed = (
                        existing["size_bytes"] != stat.st_size
                        or existing["mtime_ns"] != stat.st_mtime_ns
                        or existing["content_hash"] != content_hash
                    )
                    discovery_status = (
                        "CHANGED" if changed else existing["discovery_status"]
                    )
                    connection.execute(
                        """
                        UPDATE file_discoveries
                        SET file_kind = ?, size_bytes = ?, mtime_ns = ?,
                            content_hash = ?, discovery_status = ?,
                            availability_status = 'PRESENT', last_seen_at = ?
                        WHERE discovery_id = ?
                        """,
                        (
                            file_kind,
                            stat.st_size,
                            stat.st_mtime_ns,
                            content_hash,
                            discovery_status,
                            observed_at,
                            existing["discovery_id"],
                        ),
                    )
                    if changed:
                        _insert_event(
                            connection,
                            scan_id=scan_id,
                            discovery_id=existing["discovery_id"],
                            event_type="CHANGED",
                            observed_at=observed_at,
                            size_bytes=stat.st_size,
                            mtime_ns=stat.st_mtime_ns,
                            content_hash=content_hash,
                        )
                        changed_count += 1
                    elif existing["availability_status"] == "MISSING":
                        _insert_event(
                            connection,
                            scan_id=scan_id,
                            discovery_id=existing["discovery_id"],
                            event_type="REAPPEARED",
                            observed_at=observed_at,
                            size_bytes=stat.st_size,
                            mtime_ns=stat.st_mtime_ns,
                            content_hash=content_hash,
                        )

            for error in walk_errors:
                issue_count += 1
                _insert_issue(
                    connection,
                    scan_id=scan_id,
                    canonical_path=error.filename,
                    issue_reason="DIRECTORY_SCAN_FAILED",
                    issue_detail=str(error),
                    observed_at=observed_at,
                )

        missing_count = 0
        existing_rows = connection.execute(
            """
            SELECT discovery_id, canonical_path, availability_status
            FROM file_discoveries
            """
        ).fetchall()
        for existing in existing_rows:
            canonical_path = Path(existing["canonical_path"])
            if not _inside_any(canonical_path, config.discovery_roots):
                continue
            if (
                existing["canonical_path"] not in seen_paths
                and existing["availability_status"] != "MISSING"
            ):
                connection.execute(
                    """
                    UPDATE file_discoveries
                    SET availability_status = 'MISSING'
                    WHERE discovery_id = ?
                    """,
                    (existing["discovery_id"],),
                )
                _insert_event(
                    connection,
                    scan_id=scan_id,
                    discovery_id=existing["discovery_id"],
                    event_type="MISSING",
                    observed_at=observed_at,
                    size_bytes=None,
                    mtime_ns=None,
                    content_hash=None,
                )
                missing_count += 1

        completed_at = _utc_now()
        connection.execute(
            """
            UPDATE discovery_scans
            SET completed_at = ?, scan_status = 'COMPLETE', files_seen = ?,
                discovered_count = ?, changed_count = ?, missing_count = ?,
                unstable_count = ?, issue_count = ?, ignored_count = ?
            WHERE scan_id = ?
            """,
            (
                completed_at,
                files_seen,
                discovered_count,
                changed_count,
                missing_count,
                unstable_count,
                issue_count,
                ignored_count,
                scan_id,
            ),
        )
        candidates = connection.execute(
            """
            SELECT * FROM file_discoveries
            WHERE availability_status = 'PRESENT'
              AND discovery_status IN ('DISCOVERED', 'CHANGED')
            ORDER BY file_kind, canonical_path
            """
        ).fetchall()
        issues = connection.execute(
            """
            SELECT canonical_path, issue_reason, issue_detail, observed_at
            FROM discovery_scan_issues
            WHERE scan_id = ?
            ORDER BY canonical_path, issue_reason
            """,
            (scan_id,),
        ).fetchall()

    return {
        "scan_id": scan_id,
        "started_at": started_at,
        "completed_at": completed_at,
        "files_seen": files_seen,
        "discovered_count": discovered_count,
        "changed_count": changed_count,
        "missing_count": missing_count,
        "unstable_count": unstable_count,
        "issue_count": issue_count,
        "ignored_count": ignored_count,
        "candidates": [dict(row) for row in candidates],
        "issues": [dict(row) for row in issues],
    }


def list_discoveries(
    database_path: str | Path,
    *,
    file_kind: str | None = None,
) -> list[dict[str, Any]]:
    """Return present files awaiting registration/attachment or review."""

    if file_kind not in {None, "video", "toml"}:
        raise ValueError("file_kind must be video, toml, or null")
    if not Path(database_path).is_file():
        return []
    initialize_discovery_schema(database_path)
    query = """
        SELECT * FROM file_discoveries
        WHERE availability_status = 'PRESENT'
          AND discovery_status IN ('DISCOVERED', 'CHANGED')
    """
    parameters: tuple[str, ...] = ()
    if file_kind is not None:
        query += " AND file_kind = ?"
        parameters = (file_kind,)
    query += " ORDER BY canonical_path"
    with connect_database(database_path) as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [dict(row) for row in rows]


def mark_video_discovery_registered(
    database_path: str | Path,
    *,
    canonical_path: str | Path,
    video_id: str,
) -> None:
    """Mark a discovered video registered without inventing a discovery row."""

    initialize_discovery_schema(database_path)
    with connect_database(database_path) as connection:
        connection.execute(
            """
            UPDATE file_discoveries
            SET discovery_status = 'REGISTERED', registered_video_id = ?
            WHERE canonical_path = ? AND file_kind = 'video'
            """,
            (video_id, str(Path(canonical_path).resolve(strict=False))),
        )
