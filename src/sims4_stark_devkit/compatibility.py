from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from sims4_stark_devkit.dbpf import DBPFError, read_index


@dataclass(frozen=True)
class CompatibilityIssue:
    severity: str
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"severity": self.severity, "path": self.path, "message": self.message}


@dataclass(frozen=True)
class CompatibilityReport:
    root: str
    issues: list[CompatibilityIssue]

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warning")

    @property
    def ok(self) -> bool:
        return self.error_count == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "root": self.root,
            "ok": self.ok,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def _parse_python_37(source_text: str, source_path: Path, issues: list[CompatibilityIssue]) -> None:
    try:
        ast.parse(source_text, filename=str(source_path), feature_version=(3, 7))
    except SyntaxError as exc:
        issues.append(
            CompatibilityIssue(
                severity="error",
                path=str(source_path),
                message=f"Python 3.7 incompatible syntax: {exc.msg} at line {exc.lineno}",
            )
        )


def _scan_python_file(path: Path, issues: list[CompatibilityIssue]) -> None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    _parse_python_37(text, path, issues)


def _scan_ts4script(path: Path, issues: list[CompatibilityIssue]) -> None:
    try:
        with ZipFile(path, "r") as archive:
            names = archive.namelist()
            if not names:
                issues.append(CompatibilityIssue("warning", str(path), "Archive is empty"))
            lowered = [name.lower() for name in names]
            if len(lowered) != len(set(lowered)):
                issues.append(CompatibilityIssue("warning", str(path), "Archive has case-insensitive duplicate members"))

            script_members = [name for name in names if name.endswith((".py", ".pyc"))]
            if not script_members:
                issues.append(CompatibilityIssue("warning", str(path), "Archive contains no Python script members"))

            for member in names:
                if "__pycache__" in member:
                    issues.append(CompatibilityIssue("warning", f"{path}:{member}", "Archive contains __pycache__"))
                if member.endswith(".py"):
                    text = archive.read(member).decode("utf-8", errors="ignore")
                    _parse_python_37(text, Path(f"{path}:{member}"), issues)
    except BadZipFile:
        issues.append(CompatibilityIssue("error", str(path), "Not a valid .ts4script/.zip archive"))


def _scan_package(path: Path, issues: list[CompatibilityIssue]) -> None:
    try:
        index = read_index(path)
    except DBPFError as exc:
        issues.append(CompatibilityIssue("error", str(path), str(exc)))
        return

    if not index.entries:
        issues.append(CompatibilityIssue("warning", str(path), "Package contains zero resources"))

    unsupported = [
        entry for entry in index.entries if entry.compression_type not in {0x0000, 0x5A42, 0xFFE0, 0xFFFE, 0xFFFF}
    ]
    for entry in unsupported:
        issues.append(
            CompatibilityIssue(
                "warning",
                str(path),
                f"Unknown compression marker on resource 0x{entry.key.instance_id:016X}: 0x{entry.compression_type:04X}",
            )
        )


def scan_path(root: str | Path) -> CompatibilityReport:
    path = Path(root).resolve()
    issues: list[CompatibilityIssue] = []

    if path.is_file():
        targets = [path]
    else:
        targets = sorted(file_path for file_path in path.rglob("*") if file_path.is_file())

    for file_path in targets:
        if "__pycache__" in file_path.parts:
            issues.append(CompatibilityIssue("warning", str(file_path), "Found __pycache__ artifact"))
        if file_path.suffix == ".py":
            _scan_python_file(file_path, issues)
        elif file_path.suffix == ".ts4script":
            _scan_ts4script(file_path, issues)
        elif file_path.suffix == ".package":
            _scan_package(file_path, issues)

    return CompatibilityReport(root=str(path), issues=issues)


def report_as_json(report: CompatibilityReport) -> str:
    return json.dumps(report.to_dict(), indent=2)

