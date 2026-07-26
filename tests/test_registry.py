"""Focused tests for the Stage 1 SQLite registry core."""

import csv
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIRECTORY))

from idtracker_workflow_manager.registry import (
    DuplicateTrackingTargetError,
    create_tracking_target,
    export_tracking_targets_csv,
    export_videos_csv,
    generate_tracking_target_id,
    generate_video_id,
    initialize_database,
    upsert_video,
)


class RegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.database = self.root / "registry.sqlite"
        initialize_database(self.database)

    def test_initialize_database_creates_stage_one_schema(self) -> None:
        with sqlite3.connect(self.database) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    """
                    SELECT name FROM sqlite_master
                    WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                    """
                )
            }
            foreign_keys = connection.execute(
                "PRAGMA foreign_key_list(tracking_targets)"
            ).fetchall()

        self.assertEqual(tables, {"videos", "tracking_targets"})
        self.assertTrue(
            any(
                foreign_key[2] == "videos"
                and foreign_key[3] == "video_id"
                and foreign_key[4] == "video_id"
                for foreign_key in foreign_keys
            )
        )

    def test_video_upsert_preserves_stable_id_and_original_creator(self) -> None:
        video_path = self.root / "Camera_2_example.mp4"
        first = upsert_video(
            self.database,
            video_path,
            video_type="unknown",
            video_type_source="imported_filename",
            created_by="first-user",
        )
        updated = upsert_video(
            self.database,
            video_path,
            video_type="fight",
            video_type_source="manual",
            created_by="second-user",
            notes="Confirmed during intake.",
        )
        updated_without_note = upsert_video(
            self.database,
            video_path,
            video_type="fight",
            video_type_source="manual",
            created_by="third-user",
        )

        self.assertEqual(first["video_id"], updated["video_id"])
        self.assertEqual(updated["video_id"], generate_video_id(video_path))
        self.assertEqual(updated["created_by"], "first-user")
        self.assertEqual(updated["video_type"], "fight")
        self.assertEqual(
            updated_without_note["notes"], "Confirmed during intake."
        )

        with sqlite3.connect(self.database) as connection:
            count = connection.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        self.assertEqual(count, 1)

    def test_target_id_is_stable_and_duplicate_is_rejected(self) -> None:
        video = upsert_video(
            self.database,
            self.root / "fight.mp4",
            video_type="fight",
            created_by="tester",
        )
        target = create_tracking_target(
            self.database,
            video["video_id"],
            " b3 ",
            " FIGHT ",
            created_by="tester",
        )

        expected_id = generate_tracking_target_id(
            video["video_id"], "B3", "fight"
        )
        self.assertEqual(target["tracking_target_id"], expected_id)
        self.assertEqual(target["cell_label"], "B3")
        self.assertEqual(target["analysis_type"], "fight")

        with self.assertRaises(DuplicateTrackingTargetError):
            create_tracking_target(
                self.database,
                video["video_id"],
                "B3",
                "fight",
                created_by="tester",
            )

        with sqlite3.connect(self.database) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM tracking_targets"
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_tracking_target_requires_registered_video(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown video_id"):
            create_tracking_target(
                self.database,
                "video_missing",
                "A1",
                "ba",
                created_by="tester",
            )

    def test_csv_exports_include_rows_and_headers(self) -> None:
        video = upsert_video(
            self.database,
            self.root / "ba_video.mp4",
            video_type="ba",
            created_by="tester",
        )
        target = create_tracking_target(
            self.database,
            video["video_id"],
            "A1",
            "ba",
            created_by="tester",
        )

        videos_csv = export_videos_csv(
            self.database, self.root / "exports" / "videos.csv"
        )
        targets_csv = export_tracking_targets_csv(
            self.database, self.root / "exports" / "tracking_targets.csv"
        )

        with videos_csv.open(encoding="utf-8", newline="") as input_file:
            video_rows = list(csv.DictReader(input_file))
        with targets_csv.open(encoding="utf-8", newline="") as input_file:
            target_rows = list(csv.DictReader(input_file))

        self.assertEqual(len(video_rows), 1)
        self.assertEqual(video_rows[0]["video_id"], video["video_id"])
        self.assertEqual(video_rows[0]["video_type"], "ba")
        self.assertEqual(len(target_rows), 1)
        self.assertEqual(
            target_rows[0]["tracking_target_id"],
            target["tracking_target_id"],
        )
        self.assertEqual(target_rows[0]["final_approved"], "0")


if __name__ == "__main__":
    unittest.main()
