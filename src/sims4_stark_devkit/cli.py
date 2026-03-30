from __future__ import annotations

import argparse
import json
from pathlib import Path

from sims4_stark_devkit.compatibility import report_as_json as compatibility_report_as_json
from sims4_stark_devkit.compatibility import scan_path
from sims4_stark_devkit.dbpf import (
    COMPRESSION_UNCOMPRESSED,
    COMPRESSION_ZLIB,
    PackageWriteRequest,
    ResourceKey,
    extract_resources,
    load_manifest,
    read_index,
    write_package,
)
from sims4_stark_devkit.decompiler import decompile, report_as_json as decompile_report_as_json
from sims4_stark_devkit.scaffolding import init_project


def _resource_request(spec: str, *, zlib_enabled: bool) -> PackageWriteRequest:
    key_spec, path_spec = spec.split("=", 1)
    type_id, group_id, instance_id = key_spec.split(":")
    compression_type = COMPRESSION_ZLIB if zlib_enabled else COMPRESSION_UNCOMPRESSED
    return PackageWriteRequest(
        key=ResourceKey.from_fields(type_id, group_id, instance_id),
        path=Path(path_spec).resolve(),
        compression_type=compression_type,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stark-devkit", description="Modern Sims 4 developer toolkit")
    subparsers = parser.add_subparsers(dest="command", required=True)

    decompile_parser = subparsers.add_parser("decompile", help="Decompile ts4script/pyc inputs")
    decompile_parser.add_argument("input", help="Path to .ts4script, .zip, .pyc, or directory")
    decompile_parser.add_argument("--output", required=True, help="Output directory for decompiled .py files")
    decompile_parser.add_argument("--jobs", type=int, default=4, help="Worker count for per-file fallback passes")
    decompile_parser.add_argument("--json", action="store_true", help="Emit JSON report")

    package_read_parser = subparsers.add_parser("package-read", help="Inspect or extract a DBPF package")
    package_read_parser.add_argument("package", help="Path to .package")
    package_read_parser.add_argument("--extract", help="Directory to extract resources into")
    package_read_parser.add_argument("--raw", action="store_true", help="Extract compressed bytes without decompression")
    package_read_parser.add_argument("--json", action="store_true", help="Emit JSON summary")

    package_write_parser = subparsers.add_parser("package-write", help="Write a DBPF package")
    package_write_parser.add_argument("output", help="Destination .package path")
    package_write_parser.add_argument("--manifest", help="JSON manifest describing resources")
    package_write_parser.add_argument(
        "--resource",
        action="append",
        default=[],
        help="Inline resource spec TYPE:GROUP:INSTANCE=path",
    )
    package_write_parser.add_argument("--zlib", action="store_true", help="Compress inline --resource payloads with zlib")

    init_project_parser = subparsers.add_parser("init-project", help="Generate a new Sims 4 mod project scaffold")
    init_project_parser.add_argument("destination", help="Destination directory")
    init_project_parser.add_argument("--name", required=True, help="Human-readable project name")
    init_project_parser.add_argument("--creator", required=True, help="Creator or studio name")
    init_project_parser.add_argument("--module-name", help="Optional Python package name override")

    test_parser = subparsers.add_parser("test", help="Run compatibility checks")
    test_parser.add_argument("target", help="Project, ts4script, package, or file to test")
    test_parser.add_argument("--json", action="store_true", help="Emit JSON report")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "decompile":
        report = decompile(args.input, args.output, jobs=args.jobs)
        if args.json:
            print(decompile_report_as_json(report))
        else:
            print(f"Decompiled {report.succeeded}/{report.total_files} files into {report.output_dir}")
            if report.failed:
                print(f"Failures: {report.failed}")
        return 0 if report.failed == 0 else 2

    if args.command == "package-read":
        if args.extract:
            written = extract_resources(args.package, args.extract, raw=args.raw)
            print(f"Extracted {len(written) // 2} resources to {args.extract}")
            return 0

        index = read_index(args.package)
        if args.json:
            print(json.dumps(index.to_dict(), indent=2))
        else:
            print(f"Package: {index.path}")
            print(f"Format: {index.major_version}.{index.minor_version}")
            print(f"Resources: {len(index.entries)}")
            for entry in index.entries[:20]:
                payload = entry.to_dict()
                print(
                    f"- {payload['type']} {payload['group']} {payload['instance']} "
                    f"{payload['compression']} {payload['compressed_size']} bytes"
                )
            if len(index.entries) > 20:
                print(f"... {len(index.entries) - 20} more")
        return 0

    if args.command == "package-write":
        requests: list[PackageWriteRequest] = []
        if args.manifest:
            requests.extend(load_manifest(args.manifest))
        requests.extend(_resource_request(spec, zlib_enabled=args.zlib) for spec in args.resource)
        if not requests:
            parser.error("package-write requires --manifest or at least one --resource")
        output = write_package(args.output, list(requests))
        print(f"Wrote package: {output}")
        return 0

    if args.command == "init-project":
        project_dir = init_project(
            args.destination,
            name=args.name,
            creator=args.creator,
            module_name=args.module_name,
        )
        print(f"Created project scaffold at {project_dir}")
        return 0

    if args.command == "test":
        report = scan_path(args.target)
        if args.json:
            print(compatibility_report_as_json(report))
        else:
            print(f"Target: {report.root}")
            print(f"Errors: {report.error_count}")
            print(f"Warnings: {report.warning_count}")
            for issue in report.issues:
                print(f"- [{issue.severity}] {issue.path}: {issue.message}")
        return 0 if report.ok else 2

    parser.error(f"Unhandled command: {args.command}")
    return 2

