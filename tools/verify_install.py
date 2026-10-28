#!/usr/bin/env python3
"""Independently verify an installation against the exact original cartridge."""
import argparse
import hashlib
from pathlib import Path
import re
import struct

SUPPORTED = "4d8a3ffa13ad525db85e596d576675860a816aa77560ca87c4505451c172c60b"
NAME = re.compile(r"(?:header|arm[79]|fnt|fat|overlays[79]|file_[0-9]{6})\.bin")


def parse_manifest(path):
    lines = path.read_text(encoding="ascii").splitlines()
    if len(lines) < 5 or lines[:4] != ["vore-nx-install\t1", "rom-sha256\t" + SUPPORTED,
                                     "game-code\tCLJP", "revision\t0"]:
        raise ValueError("unknown installation identity/schema")
    if lines[4] != "name\toffset\tsize\tload\tentry\tsha256":
        raise ValueError("unknown manifest columns")
    records = {}
    for line in lines[5:]:
        fields = line.split("\t")
        if len(fields) != 6 or not NAME.fullmatch(fields[0]) or fields[0] in records:
            raise ValueError("invalid or duplicate manifest segment name")
        if not re.fullmatch(r"[0-9a-f]{64}", fields[5]):
            raise ValueError("invalid segment digest")
        values = tuple(int(value) for value in fields[1:5])
        if any(value < 0 or value > 0xffffffff for value in values):
            raise ValueError("invalid manifest numeric field")
        records[fields[0]] = (values, fields[5])
    return records


def canonical_segments(rom):
    rom.seek(0)
    header = rom.read(512)
    expected = {"header.bin": (0, 512, 0, 0)}
    for cpu, off in ((9, 0x20), (7, 0x30)):
        offset, entry, load, size = struct.unpack_from("<4I", header, off)
        expected[f"arm{cpu}.bin"] = (offset, size, load, entry)
    for name, off in (("fnt.bin", 0x40), ("fat.bin", 0x48),
                      ("overlays9.bin", 0x50), ("overlays7.bin", 0x58)):
        offset, size = struct.unpack_from("<2I", header, off)
        expected[name] = (offset, size, 0, 0)
    offset, size, _, _ = expected["fat.bin"]
    rom.seek(offset)
    for index, (begin, end) in enumerate(struct.iter_unpack("<2I", rom.read(size))):
        expected[f"file_{index:06}.bin"] = (begin, end - begin, 0, 0)
    return expected


def verify(rom_path, install):
    records = parse_manifest(install / "manifest.tsv")
    with rom_path.open("rb") as rom:
        if hashlib.file_digest(rom, "sha256").hexdigest() != SUPPORTED:
            raise ValueError("unsupported/damaged original ROM")
        expected = canonical_segments(rom)
        if records.keys() != expected.keys():
            raise ValueError("manifest inventory differs from original ROM")
        total = 0
        for name, values in expected.items():
            metadata, digest = records[name]
            if values != metadata:
                raise ValueError(f"segment metadata mismatch: {name}")
            path = install / name
            if path.is_symlink():
                raise ValueError(f"refusing symlink segment: {name}")
            offset, size, _, _ = values
            if path.stat().st_size != size:
                raise ValueError(f"segment length mismatch: {name}")
            rom.seek(offset)
            hash_value = hashlib.sha256()
            remaining = size
            with path.open("rb") as extracted:
                while remaining:
                    count = min(65536, remaining)
                    chunk = extracted.read(count)
                    if len(chunk) != count or chunk != rom.read(count):
                        raise ValueError(f"segment bytes differ from original ROM: {name}")
                    hash_value.update(chunk)
                    remaining -= count
            if hash_value.hexdigest() != digest:
                raise ValueError(f"segment manifest digest mismatch: {name}")
            total += size
    return len(records), total


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", required=True, type=Path)
    parser.add_argument("--install", required=True, type=Path)
    args = parser.parse_args()
    count, total = verify(args.rom, args.install)
    print(f"Verified {count} segments / {total} bytes against the exact ROM and manifest.")


if __name__ == "__main__":
    main()
