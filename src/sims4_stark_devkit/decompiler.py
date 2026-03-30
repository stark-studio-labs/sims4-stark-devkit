from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from zipfile import ZipFile


@dataclass(frozen=True)
class CommandAttempt:
    argv: list[str]
    succeeded: bool
    stdout: str
    stderr: str
    returncode: int
    skipped_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "argv": self.argv,
            "succeeded": self.succeeded,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "returncode": self.returncode,
            "skipped_reason": self.skipped_reason,
        }


@dataclass(frozen=True)
class CandidateOutput:
    backend: str
    path: Path
    score: int
    attempt: CommandAttempt


@dataclass(frozen=True)
class FileReport:
    source: str
    output: str | None
    backend: str | None
    score: int
    attempts: list[CommandAttempt]

    @property
    def succeeded(self) -> bool:
        return self.output is not None

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "output": self.output,
            "backend": self.backend,
            "score": self.score,
            "succeeded": self.succeeded,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
        }


@dataclass(frozen=True)
class DecompileReport:
    source: str
    output_dir: str
    total_files: int
    succeeded: int
    failed: int
    used_fastdec_archive: bool
    file_reports: list[FileReport] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "output_dir": self.output_dir,
            "total_files": self.total_files,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "used_fastdec_archive": self.used_fastdec_archive,
            "files": [file_report.to_dict() for file_report in self.file_reports],
        }


def _looks_like_python(text: str) -> bool:
    return any(marker in text for marker in ("def ", "class ", "import ", "from ", "return ", "pass"))


def _score_output(path: Path) -> int:
    text = path.read_text(encoding="utf-8", errors="ignore")
    line_count = sum(1 for line in text.splitlines() if line.strip())
    score = min(line_count, 2000)
    if _looks_like_python(text):
        score += 250
    if "Unsupported Python version" in text:
        score -= 500
    if "Parse error" in text or "decompile failed" in text.lower():
        score -= 250
    return score


def _run_command(argv: list[str], timeout: int = 120) -> CommandAttempt:
    executable = shutil.which(argv[0]) if argv and argv[0] != sys.executable else argv[0]
    if argv and argv[0] != sys.executable and executable is None:
        return CommandAttempt(argv=argv, succeeded=False, stdout="", stderr="", returncode=127, skipped_reason="missing")
    actual_argv = [executable, *argv[1:]] if executable else argv
    try:
        result = subprocess.run(actual_argv, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        return CommandAttempt(
            argv=argv,
            succeeded=False,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            returncode=124,
            skipped_reason="timeout",
        )
    return CommandAttempt(
        argv=argv,
        succeeded=result.returncode == 0,
        stdout=result.stdout,
        stderr=result.stderr,
        returncode=result.returncode,
    )


def _resolve_env_command(env_name: str, fallback: list[str]) -> list[str]:
    raw = os.environ.get(env_name)
    return shlex.split(raw) if raw else fallback


def _fastdec_attempts(source: Path, output_dir: Path) -> Iterable[list[str]]:
    base = _resolve_env_command("STARK_DEVKIT_FASTDEC_CMD", ["fastdec-ts4"])
    bases = [base]
    if base == ["fastdec-ts4"]:
        bases.extend(
            [
                ["fastdec"],
                [sys.executable, "-m", "fastdec_ts4"],
                [sys.executable, "-m", "FastDec_TS4"],
            ]
        )

    for candidate in bases:
        yield [*candidate, str(source), str(output_dir)]
        yield [*candidate, "-i", str(source), "-o", str(output_dir)]
        yield [*candidate, "--input", str(source), "--output", str(output_dir)]


def _tool_command(tool_name: str, env_name: str) -> list[str]:
    fallback = [tool_name]
    return _resolve_env_command(env_name, fallback)


def _extract_source(input_path: Path) -> tuple[Path, list[Path], tempfile.TemporaryDirectory[str] | None]:
    if input_path.is_dir():
        pyc_files = sorted(input_path.rglob("*.pyc"))
        return input_path, pyc_files, None

    if input_path.suffix.lower() == ".pyc":
        return input_path.parent, [input_path], None

    if input_path.suffix.lower() not in {".ts4script", ".zip"}:
        raise ValueError(f"Unsupported decompile input: {input_path}")

    temp_dir = tempfile.TemporaryDirectory(prefix="stark-devkit-extract-")
    root = Path(temp_dir.name)
    with ZipFile(input_path, "r") as archive:
        archive.extractall(root)
    pyc_files = sorted(root.rglob("*.pyc"))
    return root, pyc_files, temp_dir


def _expected_output_path(pyc_file: Path, source_root: Path, output_dir: Path) -> Path:
    relative = pyc_file.relative_to(source_root)
    return output_dir / relative.with_suffix(".py")


def _best_file_output(pyc_file: Path, output_path: Path) -> FileReport:
    attempts: list[CommandAttempt] = []
    candidates: list[CandidateOutput] = []

    backend_commands = [
        ("decompyle3", _tool_command("decompyle3", "STARK_DEVKIT_DECOMPYLE3_CMD")),
        ("uncompyle6", _tool_command("uncompyle6", "STARK_DEVKIT_UNCOMPYLE6_CMD")),
    ]

    for backend_name, command in backend_commands:
        with tempfile.TemporaryDirectory(prefix=f"stark-{backend_name}-") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            argv = [*command, "-o", str(temp_dir), str(pyc_file)]
            attempt = _run_command(argv)
            attempts.append(attempt)
            if attempt.skipped_reason == "missing" or not attempt.succeeded:
                continue

            produced = next(temp_dir.rglob("*.py"), None)
            if produced is None:
                continue

            score = _score_output(produced)
            candidates.append(CandidateOutput(backend=backend_name, path=produced, score=score, attempt=attempt))

    if not candidates:
        return FileReport(source=str(pyc_file), output=None, backend=None, score=0, attempts=attempts)

    best = max(candidates, key=lambda item: item.score)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(best.path.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")
    return FileReport(
        source=str(pyc_file),
        output=str(output_path),
        backend=best.backend,
        score=best.score,
        attempts=attempts,
    )


def _run_fastdec_archive(source: Path, output_dir: Path) -> tuple[bool, list[CommandAttempt]]:
    attempts: list[CommandAttempt] = []
    if source.suffix.lower() not in {".ts4script", ".zip"}:
        return False, attempts

    for argv in _fastdec_attempts(source, output_dir):
        attempt = _run_command(argv)
        attempts.append(attempt)
        if not attempt.succeeded:
            continue
        if any(output_dir.rglob("*.py")):
            return True, attempts
    return False, attempts


def decompile(source: str | Path, output_dir: str | Path, *, jobs: int = 4) -> DecompileReport:
    input_path = Path(source).resolve()
    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)

    source_root, pyc_files, cleanup = _extract_source(input_path)
    fastdec_used, fastdec_attempts = _run_fastdec_archive(input_path, destination)

    unresolved: list[tuple[Path, Path]] = []
    file_reports: list[FileReport] = []

    for pyc_file in pyc_files:
        output_path = _expected_output_path(pyc_file, source_root, destination)
        if fastdec_used and output_path.exists():
            file_reports.append(
                FileReport(
                    source=str(pyc_file),
                    output=str(output_path),
                    backend="fastdec-ts4",
                    score=_score_output(output_path),
                    attempts=fastdec_attempts,
                )
            )
        else:
            unresolved.append((pyc_file, output_path))

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as executor:
        for report in executor.map(lambda item: _best_file_output(item[0], item[1]), unresolved):
            file_reports.append(report)

    file_reports.sort(key=lambda item: item.source)
    succeeded = sum(1 for report in file_reports if report.succeeded)
    failed = len(file_reports) - succeeded

    if cleanup is not None:
        cleanup.cleanup()

    return DecompileReport(
        source=str(input_path),
        output_dir=str(destination),
        total_files=len(file_reports),
        succeeded=succeeded,
        failed=failed,
        used_fastdec_archive=fastdec_used,
        file_reports=file_reports,
    )


def report_as_json(report: DecompileReport) -> str:
    return json.dumps(report.to_dict(), indent=2)

