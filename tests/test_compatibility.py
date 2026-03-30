from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from sims4_stark_devkit.compatibility import scan_path


class CompatibilityTests(unittest.TestCase):
    def test_python_310_match_statement_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_name:
            source_path = Path(temp_dir_name) / "bad.py"
            source_path.write_text(
                "def choose(x):\n    match x:\n        case 1:\n            return 'one'\n",
                encoding="utf-8",
            )
            report = scan_path(source_path)
            self.assertFalse(report.ok)
            self.assertGreaterEqual(report.error_count, 1)

    def test_ts4script_with_python_source_is_checked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_name:
            archive_path = Path(temp_dir_name) / "test.ts4script"
            with ZipFile(archive_path, "w") as archive:
                archive.writestr("mod/main.py", "def hello():\n    return 'hi'\n")
            report = scan_path(archive_path)
            self.assertTrue(report.ok)


if __name__ == "__main__":
    unittest.main()

