#!/usr/bin/env python3
"""Offline Zig host builds; bootstrap downloads are a separate command."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
from bootstrap_host import NDS_COMMIT, PINS, WORK, digest

REPO = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=("host", "recompiler", "all"), nargs="?", default="all")
    args = parser.parse_args(argv)
    zig = WORK / "tools/zig-0.15.2/ziglang/zig.exe"
    if not zig.is_file():
        parser.error("Portable Windows x64 Zig absent; explicitly run tools/bootstrap_host.py host")
    env = os.environ.copy()
    env["ZIG_GLOBAL_CACHE_DIR"] = str(WORK / "zig-cache/global")
    env["ZIG_LOCAL_CACHE_DIR"] = str(WORK / "zig-cache/local")
    env["TEMP"] = env["TMP"] = str(WORK / "tmp")
    Path(env["TEMP"]).mkdir(parents=True, exist_ok=True)

    def run(command, cwd=REPO, expected=0):
        command = [str(x) for x in command]
        print(subprocess.list2cmdline(command), flush=True)
        result = subprocess.run(command, cwd=cwd, env=env)
        if result.returncode != expected:
            raise RuntimeError(f"Command exited {result.returncode}, expected {expected}")

    run([zig, "version"])
    common = [zig, "c++", "-target", "x86_64-windows-gnu", "-O2", "-Wall", "-Wextra"]
    if args.target in ("host", "all"):
        out = REPO / "build-host"
        out.mkdir(exist_ok=True)
        sources = ["-std=c++17", "-Werror", "-Iinclude", "source/cartridge.cpp", "source/sha256.cpp"]
        run(common + sources + ["tests/core_tests.cpp", "-o", out / "vore-tests.exe"])
        run([out / "vore-tests.exe"])
        run(common + sources + ["source/host_main.cpp", "-o", out / "vore-rom.exe"])
        run([out / "vore-rom.exe"], expected=2)
        run(common + sources + ["tests/local_rom_tests.cpp", "-o", out / "vore-local-tests.exe"])
    if args.target in ("recompiler", "all"):
        source = WORK / "sources" / f"ndsrecomp-{NDS_COMMIT}"
        core = source / "external/arm-recomp-core"
        header = WORK / "tools/tomlplusplus-3.4.0/toml.hpp"
        if not header.is_file() or digest(header) != PINS["toml"][1]:
            parser.error("Pinned toml++ missing/mismatched; explicitly bootstrap host")
        # The exact ndsrecomp v0.6.10 recompiler/CMakeLists.txt source set.
        sources = [core / "common" / name for name in
                   ("arm_decode.cpp", "thumb_decode.cpp", "arm_ir.cpp", "interpreter.cpp")]
        sources += [core / "profiles/armv5te_nds/arm_codegen.cpp"]
        sources += [source / "recompiler" / name for name in
                    ("src/main.cpp", "finder/config.cpp", "finder/function_finder.cpp",
                     "finder/reloc_scan.cpp", "support/sha1.cpp")]
        if not all(path.is_file() for path in sources):
            parser.error("Matching source/submodule absent; explicitly bootstrap host")
        includes = [source / "recompiler/finder", source / "recompiler/support",
                    source / "recompiler/armv4t", core / "common", core / "profiles/armv5te_nds"]
        command = common + ["-std=c++20", "-Wno-unused-parameter", "-isystem", header.parent]
        for include in includes:
            command += ["-I", include]
        out = WORK / "recompiler-build-direct"
        out.mkdir(parents=True, exist_ok=True)
        run(command + sources + ["-o", out / "nds_recompile.exe"])
        run([out / "nds_recompile.exe", "--codegen-identity"])
        print(f"Use aot.py --recompiler {out / 'nds_recompile.exe'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
