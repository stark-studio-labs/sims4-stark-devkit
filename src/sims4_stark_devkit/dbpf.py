from __future__ import annotations

import json
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HEADER_STRUCT = struct.Struct("<4sIIIIIIIIIII12sIQ24s")
MAGIC = b"DBPF"
INDEX_FLAG_CONST_TYPE = 0x1
INDEX_FLAG_CONST_GROUP = 0x2
INDEX_FLAG_CONST_INSTANCE_HI = 0x4
COMPRESSION_UNCOMPRESSED = 0x0000
COMPRESSION_ZLIB = 0x5A42
COMPRESSION_DELETED = 0xFFE0
COMPRESSION_STREAMABLE = 0xFFFE
COMPRESSION_INTERNAL = 0xFFFF
SUPPORTED_READ_COMPRESSIONS = {COMPRESSION_UNCOMPRESSED, COMPRESSION_ZLIB}


def _parse_int(value: str | int) -> int:
    if isinstance(value, int):
        return value
    value = value.strip()
    return int(value, 16) if value.lower().startswith("0x") else int(value)


def _compression_name(code: int) -> str:
    names = {
        COMPRESSION_UNCOMPRESSED: "uncompressed",
        COMPRESSION_ZLIB: "zlib",
        COMPRESSION_DELETED: "deleted",
        COMPRESSION_STREAMABLE: "streamable",
        COMPRESSION_INTERNAL: "internal",
    }
    return names.get(code, f"0x{code:04X}")


@dataclass(frozen=True, order=True)
class ResourceKey:
    type_id: int
    group_id: int
    instance_id: int

    @classmethod
    def from_fields(cls, type_id: str | int, group_id: str | int, instance_id: str | int) -> "ResourceKey":
        return cls(_parse_int(type_id), _parse_int(group_id), _parse_int(instance_id))

    @property
    def instance_hi(self) -> int:
        return (self.instance_id >> 32) & 0xFFFFFFFF

    @property
    def instance_lo(self) -> int:
        return self.instance_id & 0xFFFFFFFF

    def to_dict(self) -> dict[str, str]:
        return {
            "type": f"0x{self.type_id:08X}",
            "group": f"0x{self.group_id:08X}",
            "instance": f"0x{self.instance_id:016X}",
        }


@dataclass(frozen=True)
class ResourceEntry:
    key: ResourceKey
    offset: int
    compressed_size: int
    decompressed_size: int
    compression_type: int
    committed: int = 1
    extended: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = self.key.to_dict()
        payload.update(
            {
                "offset": self.offset,
                "compressed_size": self.compressed_size,
                "decompressed_size": self.decompressed_size,
                "compression": _compression_name(self.compression_type),
                "committed": self.committed,
                "extended": self.extended,
            }
        )
        return payload


@dataclass(frozen=True)
class PackageResource:
    entry: ResourceEntry
    data: bytes

    def to_manifest_item(self, file_name: str) -> dict[str, Any]:
        payload = self.entry.to_dict()
        payload["path"] = file_name
        return payload


@dataclass(frozen=True)
class PackageIndex:
    path: Path
    entries: list[ResourceEntry]
    major_version: int
    minor_version: int
    index_offset: int
    index_size: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "format": {"major": self.major_version, "minor": self.minor_version},
            "resource_count": len(self.entries),
            "index_offset": self.index_offset,
            "index_size": self.index_size,
            "resources": [entry.to_dict() for entry in self.entries],
        }


@dataclass(frozen=True)
class PackageWriteRequest:
    key: ResourceKey
    path: Path
    compression_type: int = COMPRESSION_UNCOMPRESSED


class DBPFError(ValueError):
    """Raised when a package cannot be parsed or written."""


def read_index(path: str | Path) -> PackageIndex:
    package_path = Path(path)
    with package_path.open("rb") as handle:
        header = handle.read(HEADER_STRUCT.size)
        if len(header) != HEADER_STRUCT.size:
            raise DBPFError(f"{package_path} is too small to be a DBPF package")

        unpacked = HEADER_STRUCT.unpack(header)
        magic = unpacked[0]
        if magic != MAGIC:
            raise DBPFError(f"{package_path} does not start with DBPF magic")

        major_version = unpacked[1]
        minor_version = unpacked[2]
        index_count = unpacked[9]
        index_offset_short = unpacked[10]
        index_size = unpacked[11]
        index_offset_long = unpacked[14]
        index_offset = index_offset_long or index_offset_short

        handle.seek(index_offset)
        flags_raw = handle.read(4)
        if len(flags_raw) != 4:
            raise DBPFError(f"{package_path} has a truncated DBPF index header")
        flags = struct.unpack("<I", flags_raw)[0]

        constant_type = struct.unpack("<I", handle.read(4))[0] if flags & INDEX_FLAG_CONST_TYPE else None
        constant_group = struct.unpack("<I", handle.read(4))[0] if flags & INDEX_FLAG_CONST_GROUP else None
        constant_instance_hi = struct.unpack("<I", handle.read(4))[0] if flags & INDEX_FLAG_CONST_INSTANCE_HI else None

        entries: list[ResourceEntry] = []
        for _ in range(index_count):
            type_id = constant_type if constant_type is not None else struct.unpack("<I", handle.read(4))[0]
            group_id = constant_group if constant_group is not None else struct.unpack("<I", handle.read(4))[0]
            instance_hi = (
                constant_instance_hi if constant_instance_hi is not None else struct.unpack("<I", handle.read(4))[0]
            )
            instance_lo = struct.unpack("<I", handle.read(4))[0]
            offset = struct.unpack("<I", handle.read(4))[0]
            size_and_flag = struct.unpack("<I", handle.read(4))[0]
            compressed_size = size_and_flag & 0x7FFFFFFF
            extended = bool(size_and_flag & 0x80000000)
            decompressed_size = struct.unpack("<I", handle.read(4))[0]
            if extended:
                compression_type = struct.unpack("<H", handle.read(2))[0]
                committed = struct.unpack("<H", handle.read(2))[0]
            else:
                compression_type = COMPRESSION_UNCOMPRESSED
                committed = 1

            key = ResourceKey(type_id=type_id, group_id=group_id, instance_id=(instance_hi << 32) | instance_lo)
            entries.append(
                ResourceEntry(
                    key=key,
                    offset=offset,
                    compressed_size=compressed_size,
                    decompressed_size=decompressed_size,
                    compression_type=compression_type,
                    committed=committed,
                    extended=extended,
                )
            )

    return PackageIndex(
        path=package_path,
        entries=entries,
        major_version=major_version,
        minor_version=minor_version,
        index_offset=index_offset,
        index_size=index_size,
    )


def read_resource_bytes(path: str | Path, entry: ResourceEntry, *, decompress: bool = True) -> bytes:
    package_path = Path(path)
    with package_path.open("rb") as handle:
        handle.seek(entry.offset)
        payload = handle.read(entry.compressed_size)

    if not decompress or entry.compression_type == COMPRESSION_UNCOMPRESSED:
        return payload
    if entry.compression_type == COMPRESSION_ZLIB:
        return zlib.decompress(payload)
    raise DBPFError(
        f"Unsupported compression type for extraction: {_compression_name(entry.compression_type)} "
        f"on {package_path}"
    )


def read_package(path: str | Path, *, decompress: bool = True) -> list[PackageResource]:
    index = read_index(path)
    resources: list[PackageResource] = []
    for entry in index.entries:
        data = read_resource_bytes(path, entry, decompress=decompress)
        resources.append(PackageResource(entry=entry, data=data))
    return resources


def extract_resources(path: str | Path, output_dir: str | Path, *, raw: bool = False) -> list[Path]:
    package_path = Path(path)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for resource in read_package(package_path, decompress=not raw):
        file_name = (
            f"{resource.entry.key.type_id:08X}_"
            f"{resource.entry.key.group_id:08X}_"
            f"{resource.entry.key.instance_id:016X}.bin"
        )
        target = destination / file_name
        target.write_bytes(resource.data)
        meta_target = target.with_suffix(".json")
        meta_target.write_text(json.dumps(resource.entry.to_dict(), indent=2), encoding="utf-8")
        written.extend([target, meta_target])

    return written


def load_manifest(path: str | Path, *, base_dir: str | Path | None = None) -> list[PackageWriteRequest]:
    manifest_path = Path(path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    resources = manifest.get("resources", [])
    root = Path(base_dir) if base_dir is not None else manifest_path.parent
    requests: list[PackageWriteRequest] = []

    for item in resources:
        key = ResourceKey.from_fields(item["type"], item["group"], item["instance"])
        compression = item.get("compression", "uncompressed")
        compression_type = COMPRESSION_ZLIB if compression == "zlib" else COMPRESSION_UNCOMPRESSED
        requests.append(
            PackageWriteRequest(
                key=key,
                path=(root / item["path"]).resolve(),
                compression_type=compression_type,
            )
        )

    return requests


def write_package(path: str | Path, resources: list[PackageWriteRequest]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    resource_blobs: list[tuple[ResourceEntry, bytes]] = []
    cursor = HEADER_STRUCT.size
    for request in sorted(resources, key=lambda item: item.key):
        raw_data = request.path.read_bytes()
        if request.compression_type == COMPRESSION_ZLIB:
            stored = zlib.compress(raw_data)
        elif request.compression_type == COMPRESSION_UNCOMPRESSED:
            stored = raw_data
        else:
            raise DBPFError(f"Unsupported write compression: {_compression_name(request.compression_type)}")

        entry = ResourceEntry(
            key=request.key,
            offset=cursor,
            compressed_size=len(stored),
            decompressed_size=len(raw_data),
            compression_type=request.compression_type,
            committed=1,
            extended=True,
        )
        resource_blobs.append((entry, stored))
        cursor += len(stored)

    index_offset = cursor
    index_flags = 0
    index_size = 4 + len(resource_blobs) * 32
    header = HEADER_STRUCT.pack(
        MAGIC,
        2,
        1,
        0,
        0,
        0,
        0,
        0,
        0,
        len(resource_blobs),
        index_offset,
        index_size,
        b"\x00" * 12,
        3,
        index_offset,
        b"\x00" * 24,
    )

    with target.open("wb") as handle:
        handle.write(header)
        for _, stored in resource_blobs:
            handle.write(stored)

        handle.write(struct.pack("<I", index_flags))
        for entry, _ in resource_blobs:
            size_flag = entry.compressed_size | 0x80000000
            handle.write(struct.pack("<I", entry.key.type_id))
            handle.write(struct.pack("<I", entry.key.group_id))
            handle.write(struct.pack("<I", entry.key.instance_hi))
            handle.write(struct.pack("<I", entry.key.instance_lo))
            handle.write(struct.pack("<I", entry.offset))
            handle.write(struct.pack("<I", size_flag))
            handle.write(struct.pack("<I", entry.decompressed_size))
            handle.write(struct.pack("<H", entry.compression_type))
            handle.write(struct.pack("<H", entry.committed))

    return target

