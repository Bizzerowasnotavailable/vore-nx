#!/usr/bin/env python3
"""Experimental Clang AArch64 bank objects; all output is ROM-derived/private.

Uses a locally installed Zig/Clang driver and the devkitA64 newlib headers.
Runtime linking remains devkitA64/libnx. Cross-compiler parity must be tested.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess

REPO = Path(__file__).resolve().parents[2]


def static_cpu(source):
    parts = source.stem.split("_")
    if ("arm9" in parts) == ("arm7" in parts):
        raise ValueError(f"cannot infer a unique bank CPU: {source.name}")
    return 0 if "arm9" in parts else 1


def validate_object(path):
    with path.open("rb") as f:
        header = f.read(64)
    if len(header) < 64 or header[:6] != b"\x7fELF\x02\x01" or struct.unpack_from("<HH", header, 16) != (1, 183):
        raise ValueError(f"not an ELF64 little-endian AArch64 relocatable object: {path.name}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nds", type=Path, required=True)
    ap.add_argument("--banks", type=Path, required=True)
    ap.add_argument("--zig", type=Path, required=True)
    ap.add_argument("--devkitpro", type=Path, default=Path("C:/devkitPro" if os.name == "nt" else "/opt/devkitpro"))
    ap.add_argument("--output", type=Path, default=REPO / "private/switch-llvm-banks")
    ap.add_argument("--jobs", type=int, choices=range(1, 5), default=2)
    ap.add_argument("--only", help="one generated .c basename for a compiler smoke test")
    args = ap.parse_args()
    nds, banks, zig, dkp, output = (p.resolve() for p in
        (args.nds, args.banks, args.zig, args.devkitpro, args.output))
    output.mkdir(parents=True, exist_ok=True)
    core = nds / "external/arm-recomp-core"
    includes = [banks, nds / "runner/src", core / "common",
                core / "profiles/armv5te_nds", nds / "recompiler/armv4t",
                nds / "recompiler/support", nds / "recompiler/src"]
    # C sources select the same fixed-width runtime ABI as GCC, without C++
    # library headers. No BIOS, asset or bank bytes are embedded in this tool.
    flags = ["cc", "-target", "aarch64-freestanding-none", "-mcpu=cortex_a57",
             "-O2", "-fPIE", "-ffunction-sections", "-fdata-sections",
             "-fno-stack-protector", "-std=gnu11", "-Wno-unused-parameter",
             "-D__SWITCH__", "-DNDS_SWITCH=1", "-DVORE_PRIVATE_BANKS=1",
             "-isystem", (dkp / "devkitA64/aarch64-none-elf/include").as_posix()]
    for p in includes: flags += ["-I", p.as_posix()]
    abi = hashlib.sha256()
    for directory in includes:
        for header in sorted(directory.rglob("*.h")):
            abi.update(header.as_posix().encode()); abi.update(header.read_bytes())
    abi_key = abi.hexdigest()
    sources = sorted(banks.glob("*.c"), key=lambda p: p.stat().st_size, reverse=True)
    if args.only: sources = [p for p in sources if p.name == args.only]
    if not sources: ap.error("no bank sources selected")

    def compile_source(source):
        target = output / ("bank_" + source.stem + ".o")
        meta = target.with_suffix(".json")
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        cpu = static_cpu(source)
        command = [str(zig), *flags, f"-DNDS_STATIC_CPU={cpu}", "-c", source.as_posix()]
        key = hashlib.sha256((repr(command) + abi_key + source_hash).encode()).hexdigest()
        if target.exists() and meta.exists() and json.loads(meta.read_text()).get("key") == key:
            validate_object(target)
            return
        temporary = target.with_suffix(".o.tmp")
        print(f"Clang -O2: {source.name}", flush=True)
        with target.with_suffix(".log").open("w") as log:
            subprocess.run(command + ["-o", temporary.as_posix()], stdout=log,
                           stderr=subprocess.STDOUT, check=True)
        validate_object(temporary)
        temporary.replace(target)
        meta.write_text(json.dumps({"key": key, "source_sha256": source_hash,
                                   "abi_sha256": abi_key, "static_cpu": cpu,
                                   "command": command}, indent=2))

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        list(pool.map(compile_source, sources))
    print(f"Compiled/validated {len(sources)} private AArch64 bank objects. DO NOT DISTRIBUTE.")


if __name__ == "__main__":
    main()
