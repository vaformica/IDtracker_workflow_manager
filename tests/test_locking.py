"""Tests for Firebird-side registry serialization."""

from pathlib import Path
import sys
import tempfile
import unittest


SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIRECTORY))

from idtracker_workflow_manager.locking import (
    RegistryFileLock,
    RegistryLockTimeout,
)


class RegistryLockTest(unittest.TestCase):
    def test_second_writer_times_out_while_lock_is_held(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            lock_path = Path(temporary_directory) / "registry.lock"
            with RegistryFileLock(lock_path):
                with self.assertRaises(RegistryLockTimeout):
                    with RegistryFileLock(
                        lock_path,
                        timeout_seconds=0.05,
                        poll_seconds=0.01,
                    ):
                        self.fail("second lock must not be acquired")

            with RegistryFileLock(lock_path, timeout_seconds=0.05):
                self.assertTrue(lock_path.is_file())


if __name__ == "__main__":
    unittest.main()
