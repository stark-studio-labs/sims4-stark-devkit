"""Tests for the CLI entry point."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from sims4_stark_devkit.cli import _resource_request, build_parser, main
from sims4_stark_devkit.dbpf import (
    COMPRESSION_UNCOMPRESSED,
    COMPRESSION_ZLIB,
    PackageWriteRequest,
    ResourceKey,
    write_package,
)


def _capture(fn):
    """Run fn() while capturing stdout. Returns (return_value, stdout_text)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ret = fn()
    return ret, buf.getvalue()


def _make_test_package(tmp_dir: Path) -> Path:
    resource = tmp_dir / "data.bin"
    resource.write_bytes(b"test payload")
    pkg = tmp_dir / "sample.package"
    write_package(pkg, [PackageWriteRequest(ResourceKey(0x11111111, 0x0, 0x1), resource, COMPRESSION_UNCOMPRESSED)])
    return pkg


# ── build_parser ──────────────────────────────────────────────────────


class BuildParserTests(unittest.TestCase):
    def test_all_subcommands_registered(self):
        parser = build_parser()
        subparser_actions = [
            a for a in parser._subparsers._actions
            if hasattr(a, "choices") and a.choices is not None
        ]
        choices = subparser_actions[0].choices
        for command in ("decompile", "package-read", "package-write", "init-project", "test"):
            self.assertIn(command, choices)

    def test_no_subcommand_exits_with_error(self):
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args([])


# ── _resource_request ─────────────────────────────────────────────────


class ResourceRequestTests(unittest.TestCase):
    def test_parses_type_group_instance(self):
        with tempfile.TemporaryDirectory() as tmp:
            resource = Path(tmp) / "data.bin"
            resource.write_bytes(b"x")
            req = _resource_request(f"0x12345678:0x0:0xABCDEF01={resource}", zlib_enabled=False)
            self.assertEqual(req.key.type_id, 0x12345678)
            self.assertEqual(req.key.instance_id, 0xABCDEF01)

    def test_zlib_enabled_sets_compression(self):
        with tempfile.TemporaryDirectory() as tmp:
            resource = Path(tmp) / "data.bin"
            resource.write_bytes(b"x")
            req = _resource_request(f"0x1:0x0:0x1={resource}", zlib_enabled=True)
            self.assertEqual(req.compression_type, COMPRESSION_ZLIB)

    def test_zlib_disabled_is_uncompressed(self):
        with tempfile.TemporaryDirectory() as tmp:
            resource = Path(tmp) / "data.bin"
            resource.write_bytes(b"x")
            req = _resource_request(f"0x1:0x0:0x1={resource}", zlib_enabled=False)
            self.assertEqual(req.compression_type, COMPRESSION_UNCOMPRESSED)


# ── init-project ──────────────────────────────────────────────────────


class InitProjectCLITests(unittest.TestCase):
    def test_creates_scaffold_returns_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = str(Path(tmp) / "MyMod")
            ret, out = _capture(lambda: main(["init-project", dest, "--name", "My Mod", "--creator", "TestDev"]))
            self.assertEqual(ret, 0)
            self.assertIn("Created project scaffold", out)

    def test_scaffold_files_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "MyMod"
            _capture(lambda: main(["init-project", str(dest), "--name", "My Mod", "--creator", "Dev"]))
            self.assertTrue((dest / "README.md").exists())
            self.assertTrue((dest / "pyproject.toml").exists())

    def test_module_name_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "CustomMod"
            _capture(lambda: main([
                "init-project", str(dest),
                "--name", "X", "--creator", "Y",
                "--module-name", "my_custom_mod",
            ]))
            self.assertTrue((dest / "src" / "my_custom_mod").is_dir())


# ── package-read ──────────────────────────────────────────────────────


class PackageReadCLITests(unittest.TestCase):
    def test_prints_resource_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = _make_test_package(Path(tmp))
            ret, out = _capture(lambda: main(["package-read", str(pkg)]))
            self.assertEqual(ret, 0)
            self.assertIn("Resources:", out)

    def test_json_flag_emits_valid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = _make_test_package(Path(tmp))
            ret, out = _capture(lambda: main(["package-read", str(pkg), "--json"]))
            self.assertEqual(ret, 0)
            parsed = json.loads(out)
            self.assertIn("resource_count", parsed)
            self.assertEqual(parsed["resource_count"], 1)

    def test_extract_creates_output_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pkg = _make_test_package(tmp_path)
            extract_dir = tmp_path / "extracted"
            ret, out = _capture(lambda: main(["package-read", str(pkg), "--extract", str(extract_dir)]))
            self.assertEqual(ret, 0)
            self.assertTrue(extract_dir.exists())
            self.assertIn("Extracted", out)


# ── package-write ─────────────────────────────────────────────────────


class PackageWriteCLITests(unittest.TestCase):
    def test_write_single_inline_resource(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            data = tmp_path / "payload.bin"
            data.write_bytes(b"hello")
            pkg = tmp_path / "output.package"
            spec = f"0x12345678:0x0:0x1={data}"
            ret, out = _capture(lambda: main(["package-write", str(pkg), "--resource", spec]))
            self.assertEqual(ret, 0)
            self.assertTrue(pkg.exists())
            self.assertIn("Wrote package", out)

    def test_write_from_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            data = tmp_path / "payload.bin"
            data.write_bytes(b"manifest payload")
            manifest = {
                "resources": [
                    {"type": "0x1", "group": "0x0", "instance": "0x1", "path": "payload.bin"},
                ]
            }
            manifest_path = tmp_path / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            pkg = tmp_path / "output.package"
            ret, out = _capture(lambda: main(["package-write", str(pkg), "--manifest", str(manifest_path)]))
            self.assertEqual(ret, 0)
            self.assertTrue(pkg.exists())

    def test_no_resources_exits_with_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = str(Path(tmp) / "output.package")
            with self.assertRaises(SystemExit):
                main(["package-write", pkg])


# ── decompile ─────────────────────────────────────────────────────────


class DecompileCLITests(unittest.TestCase):
    def test_empty_source_returns_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            out_dir = Path(tmp) / "out"
            src.mkdir()
            ret, text = _capture(lambda: main(["decompile", str(src), "--output", str(out_dir)]))
            self.assertEqual(ret, 0)
            self.assertIn("0/0", text)

    def test_empty_source_json_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            out_dir = Path(tmp) / "out"
            src.mkdir()
            ret, text = _capture(lambda: main(["decompile", str(src), "--output", str(out_dir), "--json"]))
            self.assertEqual(ret, 0)
            parsed = json.loads(text)
            self.assertEqual(parsed["total_files"], 0)


# ── test ─────────────────────────────────────────────────────────────


class TestSubcommandCLITests(unittest.TestCase):
    def test_clean_python_returns_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "mod.py"
            f.write_text("def hello():\n    return 'world'\n", encoding="utf-8")
            ret, _ = _capture(lambda: main(["test", str(f)]))
            self.assertEqual(ret, 0)

    def test_py310_syntax_returns_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "mod.py"
            f.write_text("match x:\n    case 1:\n        pass\n", encoding="utf-8")
            ret, _ = _capture(lambda: main(["test", str(f)]))
            self.assertEqual(ret, 2)

    def test_json_flag_emits_valid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "mod.py"
            f.write_text("def hello(): pass\n", encoding="utf-8")
            ret, text = _capture(lambda: main(["test", str(f), "--json"]))
            parsed = json.loads(text)
            self.assertIn("error_count", parsed)
            self.assertIn("ok", parsed)


if __name__ == "__main__":
    unittest.main()
