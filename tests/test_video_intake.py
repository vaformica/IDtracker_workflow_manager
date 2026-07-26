"""Tests for Stage 2 video intake and registry updates."""

from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIRECTORY))

from idtracker_workflow_manager.stills import StillGenerationError
from idtracker_workflow_manager.video_intake import (
    register_video_and_generate_still,
)


class VideoIntakeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.database = self.root / "registry.sqlite"
        self.video = self.root / "fight.mp4"
        self.video.touch()

    def _registered_video(self) -> sqlite3.Row:
        connection = sqlite3.connect(self.database)
        self.addCleanup(connection.close)
        connection.row_factory = sqlite3.Row
        row = connection.execute("SELECT * FROM videos").fetchone()
        assert row is not None
        return row

    def test_success_records_actual_fallback_frame_and_path(self) -> None:
        def fake_runner(
            command: list[str], **_: object
        ) -> subprocess.CompletedProcess[str]:
            filter_value = command[command.index("-vf") + 1]
            if filter_value.endswith(",0)"):
                Path(command[-1]).write_bytes(b"png")
                return subprocess.CompletedProcess(command, 0, "", "")
            return subprocess.CompletedProcess(command, 1, "", "too short")

        result = register_video_and_generate_still(
            self.database,
            self.video,
            video_type="fight",
            created_by="tester",
            still_output_directory=self.root / "stills",
            runner=fake_runner,
        )
        row = self._registered_video()

        self.assertEqual(result.still.frame_number, 0)
        self.assertEqual(row["video_type"], "fight")
        self.assertEqual(row["still_frame_number"], 0)
        self.assertEqual(row["still_png_path"], str(result.still.png_path))
        self.assertEqual(row["still_generation_status"], "SUCCESS")
        self.assertIsNone(row["still_generation_error"])

    def test_failure_is_recorded_in_registry(self) -> None:
        def failing_runner(
            command: list[str], **_: object
        ) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(command, 1, "", "no such frame")

        with self.assertRaises(StillGenerationError):
            register_video_and_generate_still(
                self.database,
                self.video,
                video_type="ba",
                created_by="tester",
                still_output_directory=self.root / "stills",
                runner=failing_runner,
            )
        row = self._registered_video()

        self.assertEqual(row["still_generation_status"], "FAILED")
        self.assertIn("frame 2000", row["still_generation_error"])
        self.assertIn("frame 1000", row["still_generation_error"])
        self.assertIn("frame 0", row["still_generation_error"])
        self.assertIsNone(row["still_png_path"])


if __name__ == "__main__":
    unittest.main()
