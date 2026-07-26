"""Tests for auditable daily Firebird inbox discovery."""

import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIRECTORY))

from idtracker_workflow_manager.discovery import (
    list_discoveries,
    scan_discovery_roots,
)
from idtracker_workflow_manager.firebird_config import FirebirdBackendConfig
from idtracker_workflow_manager.registry import initialize_database


class DiscoveryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name).resolve()
        self.video_root = self.root / "video_inbox"
        self.toml_root = self.root / "toml_inbox"
        self.registry_root = self.root / "registry"
        self.video_root.mkdir()
        self.toml_root.mkdir()
        self.database = self.registry_root / "database" / "registry.sqlite"
        self.config = FirebirdBackendConfig.from_mapping(
            {
                "registry_root": str(self.registry_root),
                "video_roots": [str(self.video_root)],
                "toml_roots": [str(self.toml_root)],
                "minimum_file_age_seconds": 300,
            }
        )
        initialize_database(self.database)
        self.now = 2_000_000_000.0

    def _make_old(self, path: Path) -> None:
        old_time = self.now - 600
        os.utime(path, (old_time, old_time))

    def test_scan_finds_stable_video_and_toml_but_not_partial_or_young(self) -> None:
        video = self.video_root / "daily_upload.mp4"
        video.write_bytes(b"video")
        self._make_old(video)
        toml = self.toml_root / "cell_b3.toml"
        toml.write_text("value = 1\n", encoding="utf-8")
        self._make_old(toml)
        partial = self.video_root / "still_uploading.mp4.partial"
        partial.write_bytes(b"partial")
        self._make_old(partial)
        young = self.video_root / "too_new.mp4"
        young.write_bytes(b"young")
        os.utime(young, (self.now, self.now))

        result = scan_discovery_roots(
            self.database,
            self.config,
            authenticated_user="scanner",
            now_provider=lambda: self.now,
        )

        self.assertEqual(result["discovered_count"], 2)
        self.assertEqual(result["unstable_count"], 1)
        self.assertEqual(result["issue_count"], 2)
        self.assertEqual(
            {
                (Path(issue["canonical_path"]).name, issue["issue_reason"])
                for issue in result["issues"]
            },
            {
                (partial.name, "PARTIAL_TRANSFER_NAME"),
                (young.name, "TOO_NEW_OR_CHANGING"),
            },
        )
        self.assertEqual(
            {
                (candidate["file_kind"], Path(candidate["canonical_path"]).name)
                for candidate in result["candidates"]
            },
            {("video", video.name), ("toml", toml.name)},
        )
        self.assertNotIn(
            partial.name,
            {Path(row["canonical_path"]).name for row in result["candidates"]},
        )
        self.assertNotIn(
            young.name,
            {Path(row["canonical_path"]).name for row in result["candidates"]},
        )

    def test_changed_and_missing_files_create_auditable_events(self) -> None:
        video = self.video_root / "daily_upload.mp4"
        video.write_bytes(b"video")
        self._make_old(video)
        toml = self.toml_root / "cell_b3.toml"
        toml.write_text("value = 1\n", encoding="utf-8")
        self._make_old(toml)
        scan_discovery_roots(
            self.database,
            self.config,
            authenticated_user="scanner",
            now_provider=lambda: self.now,
        )

        toml.write_text("value = 2\n", encoding="utf-8")
        self._make_old(toml)
        video.unlink()
        second = scan_discovery_roots(
            self.database,
            self.config,
            authenticated_user="scanner",
            now_provider=lambda: self.now,
        )

        self.assertEqual(second["changed_count"], 1)
        self.assertEqual(second["missing_count"], 1)
        discoveries = list_discoveries(self.database)
        self.assertEqual(len(discoveries), 1)
        self.assertEqual(discoveries[0]["canonical_path"], str(toml))
        self.assertEqual(discoveries[0]["discovery_status"], "CHANGED")

        with sqlite3.connect(self.database) as connection:
            events = [
                row[0]
                for row in connection.execute(
                    "SELECT event_type FROM discovery_events ORDER BY rowid"
                )
            ]
        self.assertEqual(
            events,
            ["DISCOVERED", "DISCOVERED", "CHANGED", "MISSING"],
        )


if __name__ == "__main__":
    unittest.main()
