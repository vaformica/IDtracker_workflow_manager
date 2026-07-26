"""Tests for Mac-side SSH requests and verified cache downloads."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIRECTORY))

from idtracker_workflow_manager.remote_backend import PROTOCOL_VERSION
from idtracker_workflow_manager.ssh_transport import (
    SSHClientConfig,
    SSHTransport,
    SSHTransportError,
    build_ssh_request_command,
    download_verified_artifact,
)


class SSHTransportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = SSHClientConfig(
            host="firebird",
            user="lab-user",
            remote_command="/shared/venv/bin/idtracker-firebird-backend",
            remote_config_path="/shared/config/backend.json",
        )

    def test_request_command_uses_batch_mode_and_remote_config(self) -> None:
        command = build_ssh_request_command(self.config)

        self.assertEqual(command[0], "ssh")
        self.assertIn("BatchMode=yes", command)
        self.assertIn("lab-user@firebird", command)
        self.assertIn(
            "--config /shared/config/backend.json --request",
            command[-1],
        )

    def test_request_validates_correlated_json_response(self) -> None:
        def fake_runner(
            command: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            request = json.loads(str(kwargs["input"]))
            response = {
                "ok": True,
                "protocol_version": PROTOCOL_VERSION,
                "request_id": request["request_id"],
                "action": request["action"],
                "data": {"authenticated_user": "lab-user"},
            }
            return subprocess.CompletedProcess(
                command, 0, json.dumps(response), ""
            )

        transport = SSHTransport(self.config, runner=fake_runner)
        result = transport.request("health")

        self.assertEqual(result, {"authenticated_user": "lab-user"})

    def test_remote_error_is_not_treated_as_success(self) -> None:
        def fake_runner(
            command: list[str], **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            request = json.loads(str(kwargs["input"]))
            response = {
                "ok": False,
                "protocol_version": PROTOCOL_VERSION,
                "request_id": request["request_id"],
                "action": request["action"],
                "error": {"code": "REGISTRY_BUSY", "message": "try later"},
            }
            return subprocess.CompletedProcess(
                command, 2, json.dumps(response), ""
            )

        with self.assertRaisesRegex(SSHTransportError, "REGISTRY_BUSY"):
            SSHTransport(self.config, runner=fake_runner).request("list_videos")

    def test_download_is_hash_verified_and_cached(self) -> None:
        content = b"remote-still-png"
        expected_hash = hashlib.sha256(content).hexdigest()

        def fake_scp(
            command: list[str], **_: object
        ) -> subprocess.CompletedProcess[str]:
            Path(command[-1]).write_bytes(content)
            return subprocess.CompletedProcess(command, 0, "", "")

        with tempfile.TemporaryDirectory() as temporary_directory:
            cache = Path(temporary_directory)
            downloaded = download_verified_artifact(
                self.config,
                remote_path="/shared/stills/video__frame_002000.png",
                expected_sha256=expected_hash,
                cache_directory=cache,
                runner=fake_scp,
            )
            self.assertEqual(downloaded.read_bytes(), content)
            self.assertTrue(downloaded.name.startswith(expected_hash))

            def must_not_run(
                command: list[str], **_: object
            ) -> subprocess.CompletedProcess[str]:
                self.fail("valid cached file should avoid another download")

            cached = download_verified_artifact(
                self.config,
                remote_path="/shared/stills/video__frame_002000.png",
                expected_sha256=expected_hash,
                cache_directory=cache,
                runner=must_not_run,
            )
            self.assertEqual(cached, downloaded)

    def test_hash_mismatch_removes_partial_download(self) -> None:
        expected_hash = hashlib.sha256(b"expected").hexdigest()

        def fake_scp(
            command: list[str], **_: object
        ) -> subprocess.CompletedProcess[str]:
            Path(command[-1]).write_bytes(b"wrong")
            return subprocess.CompletedProcess(command, 0, "", "")

        with tempfile.TemporaryDirectory() as temporary_directory:
            cache = Path(temporary_directory)
            with self.assertRaisesRegex(SSHTransportError, "hash mismatch"):
                download_verified_artifact(
                    self.config,
                    remote_path="/shared/stills/still.png",
                    expected_sha256=expected_hash,
                    cache_directory=cache,
                    runner=fake_scp,
                )
            self.assertEqual(list(cache.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
