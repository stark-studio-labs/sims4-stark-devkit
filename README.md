<div align="center">

# 🔧 sims4-stark-devkit

**One CLI to decompile, package, scaffold, and test your Sims 4 mods.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)]()
[![Made by Stark Studio Labs](https://img.shields.io/badge/made%20by-Stark%20Studio%20Labs-blueviolet)](https://github.com/stark-studio-labs)

*Built by [Stark Studio Labs](https://github.com/stark-studio-labs)*

</div>

---

## 📖 Table of Contents

- [😤 The Problem](#-the-problem)
- [💡 Why This Exists](#-why-this-exists)
- [🚀 Quick Start](#-quick-start)
- [📥 Install](#-install)
- [⚡ CLI](#-cli)
- [📖 Command Reference](#-command-reference)
  - [`decompile`](#decompile)
  - [`package-read`](#package-read)
  - [`package-write`](#package-write)
  - [`init-project`](#init-project)
  - [`test`](#test)
- [🔬 Development](#-development)
- [📝 Notes](#-notes)
- [🌐 Stark Labs Ecosystem](#-stark-labs-ecosystem)

---

## 😤 The Problem

Sims 4 mod development has a tooling problem. If you want to get serious about modding, you run into walls fast:

- **Decompiling game scripts requires installing 3 different tools manually** — FastDec, decompyle3, uncompyle6 — and praying at least one of them works on your `.pyc` files.
- **Creating `.package` files means learning binary formats or using GUI tools** — the DBPF format isn't documented well, and the GUI tools are Windows-only or abandoned.
- **Starting a new mod project means copy-pasting from templates** — outdated templates, wrong Python targets, missing `modinfo.py`, no test setup.
- **No easy way to validate your mod before testing in-game** — you find out something is broken after a 2-minute game load, not before.

`sims4-stark-devkit` fixes all of this with a single CLI.

---

## 💡 Why This Exists

The community reference repos are useful, but fragmented:

- 📚 `Sims4CommunityLibrary` is a strong framework, but not a modern devkit.
- 🔧 `Sims4ScriptingTemplate` has the best decompilation and workflow ideas, but lives as loose scripts.
- 🔗 `Sims4-Decompiler-Helper` proves the fallback-chain concept, but is stale Windows batch.
- 📦 `s4cl-template-project` is functional, but dated and tightly coupled to old project conventions.

This toolkit keeps the good parts and replaces the stale packaging model with **a single CLI** that handles everything — decompilation, packaging, scaffolding, and testing.

The package is written for modern Python `3.12+`, while helping you build assets that target The Sims 4's older embedded Python 3.7 interpreter.

---

## 🚀 Quick Start

Get up and running in under a minute:

```bash
# Install
pip install -e .

# Decompile a mod to learn from it
stark-devkit decompile path/to/mod.ts4script --output ./decompiled

# Start a new mod project
stark-devkit init-project ./MyFirstMod --name "My First Mod" --creator "YourName"

# Package your mod for testing
stark-devkit test ./MyFirstMod
```

That's it. No GUI tools, no manual file wrangling, no 15-step setup guides.

---

## 📥 Install

From the repo root:

```bash
python3 -m pip install -e .
```

Optional decompiler backends:

```bash
python3 -m pip install -e '.[decompilers]'
```

If you have a FastDec-TS4 binary or module installed, the devkit will try it first automatically. You can also point the tool at a custom FastDec command with `STARK_DEVKIT_FASTDEC_CMD`.

---

## ⚡ CLI

```bash
stark-devkit decompile INPUT --output out/decompiled
stark-devkit package-read mod.package
stark-devkit package-read mod.package --extract out/resources
stark-devkit package-write out.package --manifest package_manifest.json
stark-devkit init-project ./MyCoolMod --name "My Cool Mod" --creator "Stark Labs"
stark-devkit test ./MyCoolMod
```

---

## 📖 Command Reference

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

---

## 🔬 Development

Run the unit tests:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Run the CLI without installing:

```bash
PYTHONPATH=src python3 -m sims4_stark_devkit --help
```

---

## 📝 Notes

- The toolkit does not bundle third-party decompilers.
- DBPF writing currently emits valid uncompressed or zlib-compressed resources using the Sims 4 DBPF 2.1 layout.
- Internal Maxis string-table compression (`0xFFFF`) is detected but not rewritten by this version.

---

## 🌐 Stark Labs Ecosystem

> Everything we build for The Sims 4 modding community — open source, interconnected, and community-driven.

| Repo | What It Does | Status |
|------|-------------|--------|
| 📚 **[awesome-sims4-mods](https://github.com/stark-studio-labs/awesome-sims4-mods)** | Curated mod directory with compatibility tracking | ![Active](https://img.shields.io/badge/-active-brightgreen) |
| 🧱 **[sims4-stark-framework](https://github.com/stark-studio-labs/sims4-stark-framework)** | Modern typed modding framework (replaces S4CL patterns) | ![Active](https://img.shields.io/badge/-active-brightgreen) |
| 🔧 **[sims4-stark-devkit](https://github.com/stark-studio-labs/sims4-stark-devkit)** | CLI toolkit — decompile, package, scaffold, test | ![Active](https://img.shields.io/badge/-active-brightgreen) |
| 📦 **[sims4-mod-manager](https://github.com/stark-studio-labs/sims4-mod-manager)** | Scan, organize, and detect conflicts in your mod collection | ![Alpha](https://img.shields.io/badge/-alpha-orange) |
| 🎨 **[sims4-mod-builder](https://github.com/stark-studio-labs/sims4-mod-builder)** | Visual mod creation tool — no XML knowledge needed | ![In Dev](https://img.shields.io/badge/-in%20dev-yellow) |
| 🔬 **[sims4-mod-revival](https://github.com/stark-studio-labs/sims4-mod-revival)** | Decompile and revive abandoned community mods | ![Active](https://img.shields.io/badge/-active-brightgreen) |
| 💰 **[sims4-economy-sim](https://github.com/stark-studio-labs/sims4-economy-sim)** | Banking, bills, jobs, and stock market overhaul mod | ![Pre-Alpha](https://img.shields.io/badge/-pre--alpha-red) |

---

<div align="center">

**Built with 💚 by [Stark Studio Labs](https://github.com/stark-studio-labs)**

</div>
