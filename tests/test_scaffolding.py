from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sims4_stark_devkit.scaffolding import init_project


class ScaffoldingTests(unittest.TestCase):
    def test_init_project_creates_expected_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_name:
            project_dir = Path(temp_dir_name) / "MyMod"
            init_project(project_dir, name="My Fancy Mod", creator="Stark Labs")

            self.assertTrue((project_dir / "README.md").exists())
            self.assertTrue((project_dir / "pyproject.toml").exists())
            self.assertTrue((project_dir / "src" / "my_fancy_mod" / "modinfo.py").exists())
            self.assertTrue((project_dir / "tests" / "test_project_shape.py").exists())


if __name__ == "__main__":
    unittest.main()

