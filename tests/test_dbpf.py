from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sims4_stark_devkit.dbpf import (
    COMPRESSION_UNCOMPRESSED,
    COMPRESSION_ZLIB,
    ResourceKey,
    extract_resources,
    read_index,
    read_package,
    write_package,
    PackageWriteRequest,
)


class DBPFTests(unittest.TestCase):
    def test_roundtrip_package_write_and_read(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            resource_a = temp_dir / "a.bin"
            resource_b = temp_dir / "b.bin"
            resource_a.write_bytes(b"alpha")
            resource_b.write_bytes(b"beta" * 20)
            package_path = temp_dir / "sample.package"

            write_package(
                package_path,
                [
                    PackageWriteRequest(ResourceKey(0x11111111, 0x0, 0x1), resource_a, COMPRESSION_UNCOMPRESSED),
                    PackageWriteRequest(ResourceKey(0x22222222, 0x0, 0x2), resource_b, COMPRESSION_ZLIB),
                ],
            )

            index = read_index(package_path)
            self.assertEqual(len(index.entries), 2)
            resources = read_package(package_path)
            self.assertEqual(resources[0].data, b"alpha")
            self.assertEqual(resources[1].data, b"beta" * 20)

    def test_extract_resources_writes_payload_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            resource = temp_dir / "resource.bin"
            resource.write_bytes(b"hello package")
            package_path = temp_dir / "example.package"
            extract_dir = temp_dir / "extracted"

            write_package(
                package_path,
                [PackageWriteRequest(ResourceKey(0xABCDEF01, 0x10, 0x20), resource, COMPRESSION_UNCOMPRESSED)],
            )
            written = extract_resources(package_path, extract_dir)

            self.assertEqual(len(written), 2)
            meta_files = list(extract_dir.glob("*.json"))
            self.assertEqual(len(meta_files), 1)
            payload = json.loads(meta_files[0].read_text(encoding="utf-8"))
            self.assertEqual(payload["type"], "0xABCDEF01")


if __name__ == "__main__":
    unittest.main()

