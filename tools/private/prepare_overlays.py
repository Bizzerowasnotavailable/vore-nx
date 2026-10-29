#!/usr/bin/env python3
"""Materialise the prepared ROM images and overlay descriptors ingest expects.

`ndsrecomp/tools/ingest_coverage_manifests.py --images DIR` wants:

    arm9.bin, arm7.bin, arm9.toml, arm7.toml
    overlays/<name>.bin
    overlays.json   (a JSON *list* of {"file", "load_address"} records)

The AOT preparation step already wrote the two main images and their TOMLs but
recorded overlays as metadata only, in a different JSON shape. This derives the
missing layout from the user's own cartridge: it reads each overlay's FAT file,
decompresses it when the descriptor says it is compressed, and verifies the
result against the descriptor's declared size.

Private tooling. Output is ROM-derived and must stay under ignored paths.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import shutil
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Private working directory (runner build, generated banks, ROM images). Keep it
# configurable so this tool can live in the published source tree while the
# ROM-derived work stays outside it.
LOCAL = Path(os.environ.get("VORE_WORK") or HERE.parent).resolve()
WORKSPACE = LOCAL.parent
DEFAULT_ROM = Path(os.environ.get("VORE_ROM") or WORKSPACE / "rom.nds")
DEFAULT_AOT = (WORKSPACE / "vore-nx" / "private" / "aot"
               / "4d8a3ffa13ad525db85e596d576675860a816aa77560ca87c4505451c172c60b")
DEFAULT_WHEEL = LOCAL / "downloads" / "ndspy-4.2.0-py3-none-any.whl"
DEFAULT_OUT = LOCAL / "analysis-images"
ROM_SHA256 = "4d8a3ffa13ad525db85e596d576675860a816aa77560ca87c4505451c172c60b"


def load_ndspy(wheel: Path):
    wheel = wheel.resolve()
    if not wheel.is_file():
        raise SystemExit(f"missing pinned ndspy wheel: {wheel}")
    sys.path.insert(0, str(wheel))
    module = importlib.import_module("ndspy.codeCompression")
    if not str(module.__file__).startswith(str(wheel) + os.sep):
        raise SystemExit("ndspy did not load from the verified wheel")
    return module.decompress


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", type=Path, default=DEFAULT_ROM)
    ap.add_argument("--aot", type=Path, default=DEFAULT_AOT)
    ap.add_argument("--wheel", type=Path, default=DEFAULT_WHEEL)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    rom = args.rom.read_bytes()
    if hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise SystemExit("unsupported ROM SHA-256")

    metadata = json.loads((args.aot / "overlays.json").read_text(encoding="utf-8"))
    overlays = metadata["overlays"]
    decompress = load_ndspy(args.wheel)

    out: Path = args.out
    if out.exists() and args.force:
        shutil.rmtree(out)
    (out / "overlays").mkdir(parents=True, exist_ok=True)
    for name in ("arm9.bin", "arm7.bin", "arm9.toml", "arm7.toml"):
        source = args.aot / "inputs" / name
        if not source.is_file():
            raise SystemExit(f"missing prepared image: {source}")
        shutil.copyfile(source, out / name)

    records = []
    stats = dict(total=len(overlays), compressed=0, raw=0, bytes=0,
                 skipped_small=0, failed=[])
    for index, ova in enumerate(sorted(overlays, key=lambda o: (o["load_address"], o["id"]))):
        begin = ova["rom_offset"]
        end = begin + ova["raw_size"]
        raw = rom[begin:end]
        size = ova["size"]
        if ova["compressed_in_rom"]:
            stats["compressed"] += 1
            try:
                blob = bytes(decompress(raw))
            except Exception as error:                     # noqa: BLE001
                stats["failed"].append(dict(id=ova["id"], error=str(error)))
                continue
        else:
            stats["raw"] += 1
            blob = raw[:size] if len(raw) >= size else raw
        if len(blob) != size:
            stats["failed"].append(
                dict(id=ova["id"], error=f"size {len(blob)} != declared {size}"))
            continue
        # The seeder matches 256-byte probes, so anything shorter can never be
        # resolved to its ROM image; keep the bytes but do not pretend.
        if size < 256:
            stats["skipped_small"] += 1
        name = f"ov{ova['id']:03d}.bin"
        (out / "overlays" / name).write_bytes(blob)
        stats["bytes"] += len(blob)
        records.append(dict(file=name, load_address=f"0x{ova['load_address']:08X}",
                            size=size, bss_size=ova["bss_size"],
                            overlay_id=ova["id"],
                            static_init_start=f"0x{ova['static_init_start']:08X}",
                            static_init_end=f"0x{ova['static_init_end']:08X}",
                            sha1=hashlib.sha1(blob).hexdigest()))

    (out / "overlays.json").write_text(
        json.dumps(records, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(dict(out=str(out), records=len(records), **stats), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
