# sims4-stark-devkit

`sims4-stark-devkit` is a net-new Sims 4 developer toolkit focused on the workflows older community repos handle only partially:

- chained `.ts4script` and `.pyc` decompilation
- DBPF `.package` inspection and writing
- clean project scaffolding for new mods
- compatibility checks against the Sims 4 Python 3.7 runtime target

The package is written for modern Python `3.12+`, while helping you build assets that target The Sims 4's older embedded interpreter.

## Why this exists

The reference repos are useful, but fragmented:

- `Sims4CommunityLibrary` is a strong framework, but not a modern devkit.
- `Sims4ScriptingTemplate` has the best decompilation and workflow ideas, but lives as loose scripts.
- `Sims4-Decompiler-Helper` proves the fallback-chain concept, but is stale Windows batch.
- `s4cl-template-project` is functional, but dated and tightly coupled to old project conventions.

This toolkit keeps the good parts and replaces the stale packaging model with a single CLI.

## Install

From the repo root:

```bash
python3 -m pip install -e .
```

Optional decompiler backends:

```bash
python3 -m pip install -e '.[decompilers]'
```

If you have a FastDec-TS4 binary or module installed, the devkit will try it first automatically. You can also point the tool at a custom FastDec command with `STARK_DEVKIT_FASTDEC_CMD`.

## CLI

```bash
stark-devkit decompile INPUT --output out/decompiled
stark-devkit package-read mod.package
stark-devkit package-read mod.package --extract out/resources
stark-devkit package-write out.package --manifest package_manifest.json
stark-devkit init-project ./MyCoolMod --name "My Cool Mod" --creator "Stark Labs"
stark-devkit test ./MyCoolMod
```

## Command reference

### `decompile`

Decompile a `.ts4script`, `.zip`, `.pyc`, or directory of `.pyc` files.

```bash
stark-devkit decompile mc_cmd_center.ts4script --output ./decompiled
```

Behavior:

- tries a FastDec-style archive pass first when possible
- falls back to `decompyle3`
- falls back again to `uncompyle6`
- picks the best surviving output for each file
- emits a machine-readable JSON report with `--json`

Environment overrides:

- `STARK_DEVKIT_FASTDEC_CMD`
- `STARK_DEVKIT_DECOMPYLE3_CMD`
- `STARK_DEVKIT_UNCOMPYLE6_CMD`

### `package-read`

Read a DBPF `.package` file and print a summary or extract its resources.

```bash
stark-devkit package-read my_mod.package --json
stark-devkit package-read my_mod.package --extract ./out/resources
```

### `package-write`

Build a `.package` file from a JSON manifest or repeated `--resource` arguments.

Manifest example:

```json
{
  "resources": [
    {
      "type": "0x545AC67A",
      "group": "0x00000000",
      "instance": "0x1234567890ABCDEF",
      "path": "resources/example.xml",
      "compression": "zlib"
    }
  ]
}
```

### `init-project`

Generate a modern starter mod project with:

- `pyproject.toml`
- `src/<module>/modinfo.py`
- `src/<module>/main.py`
- `tests/`
- a compatibility-focused README

```bash
stark-devkit init-project ./ExampleMod --name "Example Mod" --creator "Stark Labs"
```

### `test`

Run static compatibility checks against a source tree, a built `.ts4script`, a `.package`, or a mixed project directory.

Checks include:

- Python syntax compatible with Python 3.7
- malformed or duplicate script archive members
- invalid or unreadable DBPF packages
- unsupported package compression markers
- accidental `__pycache__` leakage

```bash
stark-devkit test ./ExampleMod
```

## Development

Run the unit tests:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Run the CLI without installing:

```bash
PYTHONPATH=src python3 -m sims4_stark_devkit --help
```

## Notes

- The toolkit does not bundle third-party decompilers.
- DBPF writing currently emits valid uncompressed or zlib-compressed resources using the Sims 4 DBPF 2.1 layout.
- Internal Maxis string-table compression (`0xFFFF`) is detected but not rewritten by this version.

