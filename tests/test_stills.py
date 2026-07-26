"""Tests for Stage 2 ffmpeg still generation."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIRECTORY))

from idtracker_workflow_manager.stills import (
    build_ffmpeg_still_command,
    generate_still_png,
    still_output_path,
)


class StillGenerationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.video = self.root / "example.mp4"
        self.video.touch()

    def test_build_command_selects_frame_without_scaling(self) -> None:
        output = self.root / "frame.png"
        command = build_ffmpeg_still_command(
            self.video,
            output,
            2000,
            ffmpeg_executable="/opt/ffmpeg",
        )

        self.assertEqual(command[0], "/opt/ffmpeg")
        self.assertEqual(command[command.index("-i") + 1], str(self.video))
        self.assertEqual(
            command[command.index("-vf") + 1],
            "select=eq(n\\,2000)",
        )
        self.assertEqual(command[-1], str(output))
        self.assertFalse(any("scale" in argument for argument in command))

    def test_output_name_records_actual_frame(self) -> None:
        output = still_output_path(
            self.root / "stills",
            "video_abc123",
            1000,
        )
        self.assertEqual(
            output.name,
            "video_abc123__frame_001000.png",
        )

    def test_generation_falls_back_from_2000_to_1000(self) -> None:
        attempted_frames: list[int] = []

        def fake_runner(
            command: list[str], **_: object
        ) -> subprocess.CompletedProcess[str]:
            filter_value = command[command.index("-vf") + 1]
            frame = int(filter_value.rsplit(",", 1)[1].rstrip(")"))
            attempted_frames.append(frame)
            if frame == 1000:
                Path(command[-1]).write_bytes(b"png")
                return subprocess.CompletedProcess(command, 0, "", "")
            return subprocess.CompletedProcess(
                command, 1, "", "requested frame unavailable"
            )

        result = generate_still_png(
            self.video,
            self.root / "stills",
            "video_abc123",
            runner=fake_runner,
        )

        self.assertEqual(attempted_frames, [2000, 1000])
        self.assertEqual(result.frame_number, 1000)
        self.assertTrue(result.png_path.is_file())


if __name__ == "__main__":
    unittest.main()
