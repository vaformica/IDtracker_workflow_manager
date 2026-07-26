"""Versioned JSON command-line backend intended to run on Firebird."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import sqlite3
import subprocess
import sys
from typing import Any, Callable

from .firebird_config import ConfigurationError, FirebirdBackendConfig
from .locking import RegistryFileLock, RegistryLockTimeout
from .registry import (
    connect_database,
    export_videos_csv,
    initialize_database,
    record_still_failure,
    record_still_success,
    upsert_video,
)
from .stills import StillGenerationError, generate_still_png


PROTOCOL_VERSION = 1
BACKEND_NAME = "idtracker-workflow-firebird"


class ProtocolError(ValueError):
    """Raised for malformed or incompatible remote requests."""


def authenticated_unix_user() -> str:
    """Return the OS account owning the current Firebird-side process."""

    return pwd.getpwuid(os.getuid()).pw_name


def sha256_file(path: str | Path) -> str:
    """Return the SHA-256 digest for a file without loading it into memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class FirebirdBackend:
    """Authoritative registry operations executed on Firebird."""

    def __init__(
        self,
        config: FirebirdBackendConfig,
        *,
        user_provider: Callable[[], str] = authenticated_unix_user,
        still_runner: Callable[..., subprocess.CompletedProcess[str]] = (
            subprocess.run
        ),
        lock_timeout_seconds: float = 30.0,
    ) -> None:
        self.config = config
        self.user_provider = user_provider
        self.still_runner = still_runner
        self.lock_timeout_seconds = lock_timeout_seconds

    def _lock(self) -> RegistryFileLock:
        return RegistryFileLock(
            self.config.lock_path,
            timeout_seconds=self.lock_timeout_seconds,
        )

    def _audit(
        self,
        *,
        action: str,
        details: dict[str, Any],
        authenticated_user: str,
    ) -> None:
        log_path = (
            self.config.registry_root
            / "logs"
            / "remote_mutations.jsonl"
        )
        log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "occurred_at": _utc_now(),
            "authenticated_user": authenticated_user,
            "action": action,
            "details": details,
        }
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(entry, sort_keys=True) + "\n")

    def health(self) -> dict[str, Any]:
        """Return protocol and configuration information without writing files."""

        return {
            "backend": BACKEND_NAME,
            "protocol_version": PROTOCOL_VERSION,
            "authenticated_user": self.user_provider(),
            "registry_root": str(self.config.registry_root),
            "database_exists": self.config.database_path.is_file(),
            "video_roots": [str(root) for root in self.config.video_roots],
        }

    def list_directory(self, remote_path: str | None = None) -> dict[str, Any]:
        """List allowed server-side directories and video files."""

        if remote_path is None:
            return {
                "path": None,
                "entries": [
                    {
                        "name": root.name,
                        "path": str(root),
                        "kind": "root",
                    }
                    for root in self.config.video_roots
                ],
            }

        directory = self.config.canonical_video_path(
            remote_path,
            must_exist=True,
            require_file=False,
        )
        if not directory.is_dir():
            raise ConfigurationError(f"path is not a directory: {directory}")

        entries: list[dict[str, str]] = []
        for child in directory.iterdir():
            try:
                canonical_child = self.config.canonical_video_path(
                    child,
                    must_exist=True,
                    require_file=False,
                )
            except ConfigurationError:
                continue
            if canonical_child.is_dir():
                kind = "directory"
            elif (
                canonical_child.is_file()
                and canonical_child.suffix.lower()
                in self.config.video_extensions
            ):
                kind = "video"
            else:
                continue
            entries.append(
                {
                    "name": canonical_child.name,
                    "path": str(canonical_child),
                    "kind": kind,
                }
            )
        entries.sort(
            key=lambda entry: (
                entry["kind"] not in {"root", "directory"},
                entry["name"].casefold(),
            )
        )
        return {"path": str(directory), "entries": entries}

    def register_video(
        self,
        *,
        video_path: str,
        video_type: str,
    ) -> dict[str, Any]:
        canonical_path = self.config.canonical_video_path(video_path)
        authenticated_user = self.user_provider()
        with self._lock():
            initialize_database(self.config.database_path)
            video = upsert_video(
                self.config.database_path,
                canonical_path,
                video_type=video_type,
                video_type_source="manual",
                created_by=authenticated_user,
            )
            result = dict(video)
            self._audit(
                action="register_video",
                details={
                    "video_id": video["video_id"],
                    "video_path": video["video_path"],
                    "video_type": video["video_type"],
                },
                authenticated_user=authenticated_user,
            )
        return result

    def list_videos(self) -> dict[str, Any]:
        if not self.config.database_path.is_file():
            return {"videos": []}
        with self._lock(), connect_database(
            self.config.database_path
        ) as connection:
            rows = connection.execute(
                "SELECT * FROM videos ORDER BY video_path"
            ).fetchall()
        return {"videos": [dict(row) for row in rows]}

    def get_still_status(self, *, video_id: str) -> dict[str, Any]:
        if not self.config.database_path.is_file():
            raise ValueError(f"unknown video_id: {video_id}")
        with self._lock(), connect_database(
            self.config.database_path
        ) as connection:
            row = connection.execute(
                """
                SELECT video_id, video_path, still_frame_number, still_png_path,
                       still_created_at, still_hash, still_generation_status,
                       still_generation_error
                FROM videos
                WHERE video_id = ?
                """,
                (video_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"unknown video_id: {video_id}")
        return dict(row)

    def generate_still(self, *, video_id: str) -> dict[str, Any]:
        authenticated_user = self.user_provider()
        with self._lock():
            if not self.config.database_path.is_file():
                raise ValueError(f"unknown video_id: {video_id}")
            with connect_database(self.config.database_path) as connection:
                video = connection.execute(
                    "SELECT * FROM videos WHERE video_id = ?",
                    (video_id,),
                ).fetchone()
            if video is None:
                raise ValueError(f"unknown video_id: {video_id}")
            canonical_video_path = self.config.canonical_video_path(
                video["video_path"]
            )

            try:
                still = generate_still_png(
                    canonical_video_path,
                    self.config.stills_directory,
                    video_id,
                    ffmpeg_executable=self.config.ffmpeg_executable,
                    runner=self.still_runner,
                )
            except (StillGenerationError, OSError) as error:
                record_still_failure(
                    self.config.database_path,
                    video_id,
                    error_message=str(error) or type(error).__name__,
                )
                self._audit(
                    action="generate_still",
                    details={
                        "video_id": video_id,
                        "status": "FAILED",
                        "error": str(error),
                    },
                    authenticated_user=authenticated_user,
                )
                raise

            still_hash = sha256_file(still.png_path)
            updated = record_still_success(
                self.config.database_path,
                video_id,
                frame_number=still.frame_number,
                still_png_path=still.png_path,
                still_hash=still_hash,
            )
            self._audit(
                action="generate_still",
                details={
                    "video_id": video_id,
                    "status": "SUCCESS",
                    "still_frame_number": still.frame_number,
                    "still_png_path": str(still.png_path),
                    "still_hash": still_hash,
                },
                authenticated_user=authenticated_user,
            )
        return dict(updated)

    def export_videos(self) -> dict[str, Any]:
        authenticated_user = self.user_provider()
        with self._lock():
            initialize_database(self.config.database_path)
            output_path = export_videos_csv(
                self.config.database_path,
                self.config.exports_directory / "videos.csv",
            )
            output_hash = sha256_file(output_path)
            self._audit(
                action="export_videos",
                details={
                    "output_path": str(output_path),
                    "output_hash": output_hash,
                },
                authenticated_user=authenticated_user,
            )
        return {
            "output_path": str(output_path),
            "output_hash": output_hash,
        }

    def dispatch(self, action: str, parameters: dict[str, Any]) -> dict[str, Any]:
        if action == "health":
            self._require_parameters(action, parameters, allowed=frozenset())
            return self.health()
        if action == "list_directory":
            self._require_parameters(
                action, parameters, allowed=frozenset({"remote_path"})
            )
            remote_path = parameters.get("remote_path")
            if remote_path is not None and not isinstance(remote_path, str):
                raise ProtocolError("remote_path must be a string or null")
            return self.list_directory(remote_path)
        if action == "register_video":
            self._require_parameters(
                action,
                parameters,
                allowed=frozenset({"video_path", "video_type"}),
                required=frozenset({"video_path", "video_type"}),
            )
            if not isinstance(parameters["video_path"], str):
                raise ProtocolError("video_path must be a string")
            if not isinstance(parameters["video_type"], str):
                raise ProtocolError("video_type must be a string")
            return self.register_video(
                video_path=parameters["video_path"],
                video_type=parameters["video_type"],
            )
        if action == "list_videos":
            self._require_parameters(action, parameters, allowed=frozenset())
            return self.list_videos()
        if action in {"get_still_status", "generate_still"}:
            self._require_parameters(
                action,
                parameters,
                allowed=frozenset({"video_id"}),
                required=frozenset({"video_id"}),
            )
            video_id = parameters["video_id"]
            if not isinstance(video_id, str):
                raise ProtocolError("video_id must be a string")
            if action == "get_still_status":
                return self.get_still_status(video_id=video_id)
            return self.generate_still(video_id=video_id)
        if action == "export_videos":
            self._require_parameters(action, parameters, allowed=frozenset())
            return self.export_videos()
        raise ProtocolError(f"unsupported action: {action}")

    @staticmethod
    def _require_parameters(
        action: str,
        parameters: dict[str, Any],
        *,
        allowed: frozenset[str],
        required: frozenset[str] = frozenset(),
    ) -> None:
        unexpected = set(parameters) - allowed
        if unexpected:
            raise ProtocolError(
                f"unexpected parameters for {action}: "
                + ", ".join(sorted(unexpected))
            )
        missing = required - set(parameters)
        if missing:
            raise ProtocolError(
                f"missing parameters for {action}: "
                + ", ".join(sorted(missing))
            )


def handle_request(
    backend: FirebirdBackend,
    request: object,
) -> dict[str, Any]:
    """Validate one request and return a stable JSON response envelope."""

    request_id: object = None
    action: object = None
    try:
        if not isinstance(request, dict):
            raise ProtocolError("request must be a JSON object")
        request_id = request.get("request_id")
        protocol_version = request.get("protocol_version")
        if protocol_version != PROTOCOL_VERSION:
            raise ProtocolError(
                "protocol version mismatch: "
                f"client={protocol_version!r}, server={PROTOCOL_VERSION}"
            )
        action = request.get("action")
        if not isinstance(action, str) or not action:
            raise ProtocolError("action must be a non-empty string")
        parameters = request.get("parameters", {})
        if not isinstance(parameters, dict):
            raise ProtocolError("parameters must be a JSON object")
        data = backend.dispatch(action, parameters)
        return {
            "ok": True,
            "protocol_version": PROTOCOL_VERSION,
            "request_id": request_id,
            "action": action,
            "data": data,
        }
    except ProtocolError as error:
        code = "PROTOCOL_ERROR"
    except ConfigurationError as error:
        code = "PATH_OR_CONFIGURATION_ERROR"
    except RegistryLockTimeout as error:
        code = "REGISTRY_BUSY"
    except (StillGenerationError, ValueError) as error:
        code = "ACTION_ERROR"
    except (OSError, sqlite3.Error) as error:
        code = "BACKEND_ERROR"
    return {
        "ok": False,
        "protocol_version": PROTOCOL_VERSION,
        "request_id": request_id,
        "action": action,
        "error": {"code": code, "message": str(error)},
    }


def dry_run_checks(config: FirebirdBackendConfig) -> dict[str, Any]:
    """Inspect deployment prerequisites without creating or modifying files."""

    if os.path.sep in config.ffmpeg_executable:
        ffmpeg_found = (
            Path(config.ffmpeg_executable).is_file()
            and os.access(config.ffmpeg_executable, os.X_OK)
        )
    else:
        ffmpeg_found = shutil.which(config.ffmpeg_executable) is not None

    checks = {
        "registry_root_exists": config.registry_root.is_dir(),
        "registry_parent_exists": config.registry_root.parent.is_dir(),
        "all_video_roots_exist": all(
            root.is_dir() for root in config.video_roots
        ),
        "ffmpeg_found": ffmpeg_found,
        "database_exists": config.database_path.is_file(),
    }
    return {
        "ok": all(
            checks[name]
            for name in (
                "registry_parent_exists",
                "all_video_roots_exist",
                "ffmpeg_found",
            )
        ),
        "protocol_version": PROTOCOL_VERSION,
        "checks": checks,
        "database_path": str(config.database_path),
        "lock_path": str(config.lock_path),
        "warning": (
            "This dry run cannot prove network-filesystem locking safety. "
            "Confirm the fixed Firebird host and single-writer design before "
            "creating real registry data."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    """Run one JSON request or a read-only deployment dry run."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="backend JSON config")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--request",
        action="store_true",
        help="read one JSON request from stdin and write one JSON response",
    )
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="check configuration without creating files",
    )
    args = parser.parse_args(argv)

    try:
        config = FirebirdBackendConfig.from_json_file(args.config)
        if args.dry_run:
            result = dry_run_checks(config)
            print(json.dumps(result, sort_keys=True))
            return 0 if result["ok"] else 1

        try:
            request = json.load(sys.stdin)
        except json.JSONDecodeError as error:
            response = {
                "ok": False,
                "protocol_version": PROTOCOL_VERSION,
                "request_id": None,
                "action": None,
                "error": {
                    "code": "INVALID_JSON",
                    "message": str(error),
                },
            }
        else:
            response = handle_request(FirebirdBackend(config), request)
        print(json.dumps(response, sort_keys=True))
        return 0 if response["ok"] else 2
    except ConfigurationError as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "protocol_version": PROTOCOL_VERSION,
                    "error": {
                        "code": "CONFIGURATION_ERROR",
                        "message": str(error),
                    },
                },
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
