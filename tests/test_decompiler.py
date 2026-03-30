"""Tests for the decompiler module."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from sims4_stark_devkit.decompiler import (
    DecompileReport,
    FileReport,
    _expected_output_path,
    _extract_source,
    _looks_like_python,
    _resolve_env_command,
    _run_command,
    _score_output,
    decompile,
    report_as_json,
)


# ── _looks_like_python ────────────────────────────────────────────────


class LooksPythonTests(unittest.TestCase):
    def test_def_keyword_detected(self):
        self.assertTrue(_looks_like_python("def foo(): pass"))

    def test_class_keyword_detected(self):
        self.assertTrue(_looks_like_python("class Foo:"))

    def test_import_keyword_detected(self):
        self.assertTrue(_looks_like_python("import os"))

    def test_from_import_detected(self):
        self.assertTrue(_looks_like_python("from pathlib import Path"))

    def test_return_keyword_detected(self):
        self.assertTrue(_looks_like_python("    return None"))

    def test_empty_string_not_python(self):
        self.assertFalse(_looks_like_python(""))

    def test_non_python_text_returns_false(self):
        self.assertFalse(_looks_like_python("hello world no keywords here"))


# ── _score_output ─────────────────────────────────────────────────────


class ScoreOutputTests(unittest.TestCase):
    def test_empty_file_scores_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "empty.py"
            f.write_text("", encoding="utf-8")
            self.assertEqual(_score_output(f), 0)

    def test_python_markers_increase_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good.py"
            plain = Path(tmp) / "plain.py"
            good.write_text("def foo():\n    return 1\n", encoding="utf-8")
            plain.write_text("some_text\nno keywords\n", encoding="utf-8")
            self.assertGreater(_score_output(good), _score_output(plain))

    def test_unsupported_version_penalizes_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "bad.py"
            f.write_text("Unsupported Python version\n", encoding="utf-8")
            self.assertLess(_score_output(f), 0)

    def test_parse_error_penalizes_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "bad.py"
            f.write_text("Parse error on line 1\n", encoding="utf-8")
            self.assertLess(_score_output(f), 0)

    def test_long_file_line_count_capped_at_2000(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "long.py"
            # 3000 non-empty lines, no python markers → min(3000, 2000) = 2000
            f.write_text("\n".join("x" for _ in range(3000)), encoding="utf-8")
            self.assertEqual(_score_output(f), 2000)


# ── _run_command ──────────────────────────────────────────────────────


class RunCommandTests(unittest.TestCase):
    def test_echo_succeeds(self):
        attempt = _run_command(["echo", "hello"])
        self.assertTrue(attempt.succeeded)
        self.assertEqual(attempt.returncode, 0)

    def test_missing_command_returns_skipped(self):
        attempt = _run_command(["__nonexistent_stark_devkit_test__"])
        self.assertFalse(attempt.succeeded)
        self.assertEqual(attempt.skipped_reason, "missing")
        self.assertEqual(attempt.returncode, 127)

    def test_failing_command_returns_nonzero(self):
        attempt = _run_command([sys.executable, "-c", "import sys; sys.exit(1)"])
        self.assertFalse(attempt.succeeded)
        self.assertEqual(attempt.returncode, 1)

    def test_stdout_captured(self):
        attempt = _run_command([sys.executable, "-c", "print('stark_devkit_test_output')"])
        self.assertIn("stark_devkit_test_output", attempt.stdout)

    def test_stderr_captured(self):
        attempt = _run_command([sys.executable, "-c", "import sys; sys.stderr.write('err_devkit')"])
        self.assertIn("err_devkit", attempt.stderr)

    def test_to_dict_contains_required_keys(self):
        attempt = _run_command(["echo", "x"])
        d = attempt.to_dict()
        for key in ("argv", "succeeded", "stdout", "stderr", "returncode", "skipped_reason"):
            self.assertIn(key, d)


# ── _resolve_env_command ──────────────────────────────────────────────


class ResolveEnvCommandTests(unittest.TestCase):
    _ENV_KEY = "STARK_DEVKIT_TEST_CMD_UNUSED_XYZ"

    def setUp(self):
        os.environ.pop(self._ENV_KEY, None)

    def tearDown(self):
        os.environ.pop(self._ENV_KEY, None)

    def test_returns_fallback_when_env_not_set(self):
        result = _resolve_env_command(self._ENV_KEY, ["fallback-tool"])
        self.assertEqual(result, ["fallback-tool"])

    def test_returns_parsed_env_when_set(self):
        os.environ[self._ENV_KEY] = "custom-tool --flag value"
        result = _resolve_env_command(self._ENV_KEY, ["fallback-tool"])
        self.assertEqual(result, ["custom-tool", "--flag", "value"])


# ── _extract_source ───────────────────────────────────────────────────


class ExtractSourceTests(unittest.TestCase):
    def test_directory_returns_all_pyc_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "a.pyc").write_bytes(b"\x00")
            sub = d / "sub"
            sub.mkdir()
            (sub / "b.pyc").write_bytes(b"\x00")
            root, pyc_files, cleanup = _extract_source(d)
            self.assertIsNone(cleanup)
            self.assertEqual(len(pyc_files), 2)

    def test_single_pyc_returns_itself(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "mod.pyc"
            f.write_bytes(b"\x00")
            root, pyc_files, cleanup = _extract_source(f)
            self.assertIsNone(cleanup)
            self.assertEqual(pyc_files, [f])

    def test_ts4script_extracts_and_returns_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "mod.ts4script"
            with ZipFile(archive, "w") as z:
                z.writestr("mod/a.pyc", b"\x00\x01")
                z.writestr("mod/b.pyc", b"\x00\x02")
            root, pyc_files, cleanup = _extract_source(archive)
            self.assertIsNotNone(cleanup)
            self.assertEqual(len(pyc_files), 2)
            cleanup.cleanup()

    def test_unsupported_extension_raises_value_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "mod.exe"
            f.write_bytes(b"\x00")
            with self.assertRaises(ValueError):
                _extract_source(f)


# ── _expected_output_path ─────────────────────────────────────────────


class ExpectedOutputPathTests(unittest.TestCase):
    def test_pyc_maps_to_py_under_output_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "src"
            out = Path(tmp) / "out"
            pyc = root / "pkg" / "mod.pyc"
            result = _expected_output_path(pyc, root, out)
            self.assertEqual(result, out / "pkg" / "mod.py")


# ── FileReport ────────────────────────────────────────────────────────


class FileReportTests(unittest.TestCase):
    def test_succeeded_true_when_output_present(self):
        report = FileReport(source="a.pyc", output="a.py", backend="uncompyle6", score=100, attempts=[])
        self.assertTrue(report.succeeded)

    def test_succeeded_false_when_output_none(self):
        report = FileReport(source="a.pyc", output=None, backend=None, score=0, attempts=[])
        self.assertFalse(report.succeeded)

    def test_to_dict_includes_all_fields(self):
        report = FileReport(source="a.pyc", output="a.py", backend="decompyle3", score=200, attempts=[])
        d = report.to_dict()
        self.assertEqual(d["source"], "a.pyc")
        self.assertEqual(d["backend"], "decompyle3")
        self.assertTrue(d["succeeded"])
        self.assertEqual(d["score"], 200)

    def test_to_dict_none_output(self):
        report = FileReport(source="b.pyc", output=None, backend=None, score=0, attempts=[])
        d = report.to_dict()
        self.assertIsNone(d["output"])
        self.assertFalse(d["succeeded"])


# ── DecompileReport ───────────────────────────────────────────────────


class DecompileReportTests(unittest.TestCase):
    def test_to_dict_structure(self):
        report = DecompileReport(
            source="mod.ts4script",
            output_dir="/out",
            total_files=3,
            succeeded=2,
            failed=1,
            used_fastdec_archive=False,
            file_reports=[],
        )
        d = report.to_dict()
        self.assertEqual(d["total_files"], 3)
        self.assertEqual(d["succeeded"], 2)
        self.assertEqual(d["failed"], 1)
        self.assertFalse(d["used_fastdec_archive"])

    def test_report_as_json_produces_valid_json(self):
        report = DecompileReport(
            source="mod.ts4script",
            output_dir="/out",
            total_files=0,
            succeeded=0,
            failed=0,
            used_fastdec_archive=False,
        )
        parsed = json.loads(report_as_json(report))
        self.assertIn("total_files", parsed)
        self.assertEqual(parsed["total_files"], 0)


# ── decompile() integration ───────────────────────────────────────────


class DecompileIntegrationTests(unittest.TestCase):
    def test_empty_directory_zero_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            out = Path(tmp) / "out"
            src.mkdir()
            report = decompile(src, out)
            self.assertEqual(report.total_files, 0)
            self.assertEqual(report.succeeded, 0)
            self.assertEqual(report.failed, 0)

    def test_ts4script_with_no_pyc_zero_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "empty.ts4script"
            with ZipFile(archive, "w") as z:
                z.writestr("README.txt", "no pyc here")
            out = Path(tmp) / "out"
            report = decompile(archive, out)
            self.assertEqual(report.total_files, 0)

    def test_report_serializes_to_valid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            out = Path(tmp) / "out"
            src.mkdir()
            report = decompile(src, out)
            parsed = json.loads(report_as_json(report))
            self.assertIn("total_files", parsed)
            self.assertIn("files", parsed)


if __name__ == "__main__":
    unittest.main()
