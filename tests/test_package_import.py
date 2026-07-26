"""Stage 0 smoke tests for the package skeleton."""

from pathlib import Path
import sys
import unittest


SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIRECTORY))

import idtracker_workflow_manager


class PackageImportTest(unittest.TestCase):
    def test_package_import_exposes_version(self) -> None:
        self.assertEqual(idtracker_workflow_manager.__version__, "0.1.0")


if __name__ == "__main__":
    unittest.main()
