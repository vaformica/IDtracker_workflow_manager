"""Tests for the Stage 3 Firebird JSON backend."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIRECTORY))

from idtracker_workflow_manager.firebird_config import FirebirdBackendConfig
from idtracker_workflow_manager.remote_backend import (
    PROTOCOL_VERSION,
    FirebirdBackend,
    handle_request,
)


class RemoteBackendTest(unittest.TestCase):
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
                "ffmpeg_executable": "/fake/ffmpeg",
                "minimum_file_age_seconds": 0,
            }
        )
        self.backend = FirebirdBackend(
            self.config,
            user_provider=lambda: "authenticated-lab-user",
            still_runner=self._fake_ffmpeg,
        )

    @staticmethod
    def _fake_ffmpeg(
        command: list[str], **_: object
    ) -> subprocess.CompletedProcess[str]:
        filter_value = command[command.index("-vf") + 1]
        if filter_value.endswith(",2000)"):
            Path(command[-1]).write_bytes(b"verified-png-content")
            return subprocess.CompletedProcess(command, 0, "", "")
        return subprocess.CompletedProcess(command, 1, "", "unavailable")

    def _request(self, action: str, parameters: dict[str, object]) -> dict:
        return handle_request(
            self.backend,
            {
                "protocol_version": PROTOCOL_VERSION,
                "request_id": "test-request",
                "action": action,
                "parameters": parameters,
            },
        )

    def test_health_reports_authenticated_remote_user_without_writes(self) -> None:
        response = self._request("health", {})

        self.assertTrue(response["ok"])
        self.assertEqual(
            response["data"]["authenticated_user"],
            "authenticated-lab-user",
        )
        self.assertFalse(self.registry_root.exists())

    def test_remote_browsing_is_limited_to_configured_root(self) -> None:
        nested = self.video_root / "day_1"
        nested.mkdir()
        (nested / "fight.mp4").touch()
        (nested / "notes.txt").touch()

        response = self._request(
            "list_directory", {"remote_path": str(nested)}
        )

        self.assertTrue(response["ok"])
        self.assertEqual(
            response["data"]["entries"],
            [
                {
                    "name": "fight.mp4",
                    "path": str(nested / "fight.mp4"),
                    "kind": "video",
                }
            ],
        )

        outside_response = self._request(
            "list_directory", {"remote_path": str(self.root)}
        )
        self.assertFalse(outside_response["ok"])
        self.assertEqual(
            outside_response["error"]["code"],
            "PATH_OR_CONFIGURATION_ERROR",
        )

    def test_register_and_generate_still_use_server_identity_and_hash(self) -> None:
        video = self.video_root / "fight.mp4"
        video.touch()
        registered = self._request(
            "register_video",
            {"video_path": str(video), "video_type": "fight"},
        )
        self.assertTrue(registered["ok"])
        video_id = registered["data"]["video_id"]

        generated = self._request(
            "generate_still", {"video_id": video_id}
        )
        self.assertTrue(generated["ok"])
        expected_hash = hashlib.sha256(b"verified-png-content").hexdigest()
        self.assertEqual(generated["data"]["still_hash"], expected_hash)
        self.assertEqual(generated["data"]["still_frame_number"], 2000)
        self.assertTrue(Path(generated["data"]["still_png_path"]).is_file())

        with sqlite3.connect(self.config.database_path) as connection:
            created_by, stored_hash = connection.execute(
                "SELECT created_by, still_hash FROM videos"
            ).fetchone()
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        self.assertEqual(created_by, "authenticated-lab-user")
        self.assertEqual(stored_hash, expected_hash)
        self.assertEqual(integrity, "ok")

        audit_entries = [
            json.loads(line)
            for line in (
                self.registry_root / "logs" / "remote_mutations.jsonl"
            ).read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(
            {entry["authenticated_user"] for entry in audit_entries},
            {"authenticated-lab-user"},
        )
        self.assertEqual(
            [entry["action"] for entry in audit_entries],
            ["register_video", "generate_still"],
        )

    def test_client_cannot_supply_created_by(self) -> None:
        video = self.video_root / "fight.mp4"
        video.touch()
        response = self._request(
            "register_video",
            {
                "video_path": str(video),
                "video_type": "fight",
                "created_by": "pretend-user",
            },
        )

        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "PROTOCOL_ERROR")
        self.assertFalse(self.registry_root.exists())

    def test_scan_lists_new_video_without_registering_it(self) -> None:
        video = self.video_root / "globus_upload.mp4"
        video.touch()

        scan = self._request("scan_files", {})
        self.assertTrue(scan["ok"])
        self.assertEqual(scan["data"]["discovered_count"], 1)

        discoveries = self._request(
            "list_discoveries", {"file_kind": "video"}
        )
        self.assertEqual(
            discoveries["data"]["discoveries"][0]["canonical_path"],
            str(video),
        )
        videos = self._request("list_videos", {})
        self.assertEqual(videos["data"]["videos"], [])

        registered = self._request(
            "register_video",
            {"video_path": str(video), "video_type": "fight"},
        )
        self.assertTrue(registered["ok"])
        after_registration = self._request(
            "list_discoveries", {"file_kind": "video"}
        )
        self.assertEqual(
            after_registration["data"]["discoveries"],
            [],
        )

    def test_protocol_version_mismatch_is_rejected(self) -> None:
        response = handle_request(
            self.backend,
            {
                "protocol_version": PROTOCOL_VERSION + 1,
                "action": "health",
                "parameters": {},
            },
        )
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "PROTOCOL_ERROR")

    def test_concurrent_remote_registrations_are_serialized_and_valid(self) -> None:
        videos = [
            self.video_root / "camera_1.mp4",
            self.video_root / "camera_2.mp4",
        ]
        for video in videos:
            video.touch()

        def register(video: Path) -> dict:
            return self._request(
                "register_video",
                {"video_path": str(video), "video_type": "fight"},
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(register, videos))

        self.assertTrue(all(response["ok"] for response in responses))
        with sqlite3.connect(self.config.database_path) as connection:
            count = connection.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        self.assertEqual(count, 2)
        self.assertEqual(integrity, "ok")


if __name__ == "__main__":
    unittest.main()
