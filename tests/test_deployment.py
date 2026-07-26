"""Integration tests for the backend CLI and deployment dry run."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SRC_DIRECTORY = REPOSITORY_ROOT / "src"


class DeploymentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name).resolve()
        self.video_root = self.root / "videos"
        self.toml_root = self.root / "tomls"
        self.video_root.mkdir()
        self.toml_root.mkdir()
        self.config_path = self.root / "backend.json"
        self.config_path.write_text(
            json.dumps(
                {
                    "registry_root": str(self.root / "registry"),
                    "video_roots": [str(self.video_root)],
                    "toml_roots": [str(self.toml_root)],
                    "ffmpeg_executable": sys.executable,
                }
            ),
            encoding="utf-8",
        )

    def test_backend_cli_health_request_is_valid_json_and_read_only(self) -> None:
        request = {
            "protocol_version": 1,
            "request_id": "integration-check",
            "action": "health",
            "parameters": {},
        }
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(SRC_DIRECTORY)

        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "idtracker_workflow_manager.remote_backend",
                "--config",
                str(self.config_path),
                "--request",
            ],
            input=json.dumps(request),
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        response = json.loads(completed.stdout)
        self.assertTrue(response["ok"])
        self.assertEqual(response["request_id"], "integration-check")
        self.assertFalse((self.root / "registry").exists())

    def test_install_bundle_dry_run_creates_nothing(self) -> None:
        install_prefix = self.root / "installation"
        completed = subprocess.run(
            [
                "bash",
                str(
                    REPOSITORY_ROOT
                    / "deployment"
                    / "firebird"
                    / "install_backend.sh"
                ),
                "--prefix",
                str(install_prefix),
                "--source",
                str(REPOSITORY_ROOT),
                "--config",
                str(self.config_path),
                "--dry-run",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Would create virtual environment", completed.stdout)
        self.assertFalse(install_prefix.exists())


if __name__ == "__main__":
    unittest.main()
