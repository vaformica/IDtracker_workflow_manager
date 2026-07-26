"""Tests for canonical Firebird configuration and path boundaries."""

from pathlib import Path
import sys
import tempfile
import unittest


SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIRECTORY))

from idtracker_workflow_manager.firebird_config import (
    ConfigurationError,
    FirebirdBackendConfig,
)


class FirebirdConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name).resolve()
        self.video_root = self.root / "videos"
        self.video_root.mkdir()
        self.registry_root = self.root / "registry"
        self.config = FirebirdBackendConfig.from_mapping(
            {
                "registry_root": str(self.registry_root),
                "video_roots": [str(self.video_root)],
            }
        )

    def test_canonical_video_path_accepts_only_allowed_video_files(self) -> None:
        video = self.video_root / "fight.mp4"
        video.touch()

        self.assertEqual(self.config.canonical_video_path(video), video)

        outside = self.root / "outside.mp4"
        outside.touch()
        with self.assertRaisesRegex(ConfigurationError, "outside configured"):
            self.config.canonical_video_path(outside)

        unsupported = self.video_root / "notes.txt"
        unsupported.touch()
        with self.assertRaisesRegex(ConfigurationError, "unsupported"):
            self.config.canonical_video_path(unsupported)

    def test_configuration_rejects_relative_authoritative_paths(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "must be absolute"):
            FirebirdBackendConfig.from_mapping(
                {
                    "registry_root": "relative/registry",
                    "video_roots": [str(self.video_root)],
                }
            )


if __name__ == "__main__":
    unittest.main()
