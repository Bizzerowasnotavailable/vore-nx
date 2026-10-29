#!/usr/bin/env python3
"""Build the experimental Switch runtime from local, ROM-owner dependencies.

No downloads. --banks produces a ROM-derived NRO which MUST NOT be published.
Without --banks, only FreeBIOS banks and the cartridge interpreter are linked.
Neither output replaces the published installer release.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[2]
FRONTEND = Path(__file__).resolve().parent / "switch_runtime"
DEFAULT_DKP = os.environ.get("DEVKITPRO", "C:/devkitPro" if os.name == "nt" else "/opt/devkitpro")
if os.name == "nt" and DEFAULT_DKP == "/opt/devkitpro":
    DEFAULT_DKP = "C:/devkitPro"  # MSYS mount name inherited by native Python.
CORE_UNITS = """runtime_arm runtime_abi_shims bus cp15 scheduler tier3 io spu vram
gpu2d gpu3d cart_backup direct_boot generated_firmware firmware_state
firmware_user_settings title_patches dispatch_timing emu_profile pc_profile
coverage_manifest diagnostics savestate savestate_slots live_overlay
battery_save host_profile host_prof_ring perf_governor profile_report
relative_mouse_touch network_savestate_guard""".split()
BIG_BYTES = 12_000_000


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nds", type=Path, required=True, help="local ndsrecomp 0.6.10 source")
    ap.add_argument("--bios-banks", type=Path, required=True,
                    help="locally generated FreeBIOS C banks (no live-byte validation)")
    ap.add_argument("--banks", type=Path, help="PRIVATE ROM-derived title-bank directory")
    ap.add_argument("--output", type=Path, default=REPO / "private/switch-runtime")
    ap.add_argument("--devkitpro", type=Path,
                    default=Path(DEFAULT_DKP))
    ap.add_argument("--jobs", type=int, choices=range(1, 9), default=2)
    ap.add_argument("--optimization", choices=("O2", "O3"), default="O2")
    ap.add_argument("--lto", action="store_true", help="experimental runtime link-time optimization (no fast-math)")
    ap.add_argument("--runtime-only", action="store_true", help="compile runtime/registry objects, omit game-bank compilation/linking")
    ap.add_argument("--minimal-profiling", action="store_true", help="omit fine-grained host timing; keep guest counters and coarse frame timings")
    ap.add_argument("--bank-lto", action="store_true", help="experimental whole-runtime/bank LTO; requires --lto and --banks, potentially expensive")
    args = ap.parse_args()
    if args.bank_lto and (not args.lto or not args.banks or args.runtime_only):
        ap.error("--bank-lto requires --lto, --banks, and a full link (not --runtime-only)")
    nds, bios, out, dkp = (p.resolve() for p in
                           (args.nds, args.bios_banks, args.output, args.devkitpro))
    banks = args.banks.resolve() if args.banks else None
    obj = out / ("obj-private" if banks else "obj-interpreter")
    obj.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["DEVKITPRO"] = dkp.as_posix()
    env["PATH"] = os.pathsep.join((str(dkp / "devkitA64/bin"),
                                    str(dkp / "tools/bin"), env.get("PATH", "")))
    suffix = ".exe" if os.name == "nt" else ""
    gcc = dkp / ("devkitA64/bin/aarch64-none-elf-gcc" + suffix)
    gxx = dkp / ("devkitA64/bin/aarch64-none-elf-g++" + suffix)
    for compiler in (gcc, gxx):
        if not compiler.is_file():
            ap.error(f"missing compiler: {compiler}")
    src = nds / "runner/src"
    core = nds / "external/arm-recomp-core"
    includes = [src, bios, FRONTEND, REPO / "include", core / "common",
                core / "profiles/armv5te_nds", nds / "recompiler/armv4t",
                nds / "recompiler/support", nds / "recompiler/src",
                nds / "runner/vendor/melonds", nds / "vendor/freebios",
                dkp / "libnx/include"]
    if banks:
        includes.append(banks)
    units = [(src / f"{name}.cpp", f"core_{name}", False) for name in CORE_UNITS]
    units += [(core / "common" / f"{name}.cpp", f"arc_{name}", False)
              for name in ("arm_decode", "thumb_decode", "arm_ir", "interpreter")]
    units += [(core / "profiles/armv5te_nds/arm_codegen.cpp", "arc_arm_codegen", False)]
    units += [(src / "net" / f"{name}.cpp", name, False)
              for name in ("net_ring", "net_classify")]
    units += [(nds / "runner/vendor/melonds" / f"{name}.cpp", f"melonds_{name}", False)
              for name in ("GPU3D", "GPU3D_Soft", "Savestate")]
    units += [(nds / "vendor/freebios/freebios_images.cpp", "freebios_images", False),
              (nds / "recompiler/support/sha1.cpp", "support_sha1", False)]
    units += [(FRONTEND / f"{name}.cpp", name, False) for name in
              ("switch_main", "switch_wifi_stub", "switch_host_info", "nds_host_shims")]
    units += [(bios / f"freebios_{cpu}{tail}.c", f"bios_{cpu}{tail}", False)
              for cpu in ("arm9", "arm7") for tail in ("", "_dispatch")]
    if banks:
        if not list(banks.glob("*_dispatch.c")):
            ap.error("--banks directory has no dispatch tables")
        registry = obj / "title_bank_registry.cpp"
        subprocess.run([sys.executable, str(Path(__file__).with_name("gen_switch_registry.py")),
                        str(banks), "--out", str(registry)], check=True)
        units.append((registry, "title_bank_registry", False))
        if not args.runtime_only:
            units += [(p, "bank_" + p.stem, True) for p in sorted(banks.glob("*.c"))]
    for path, _, _ in units:
        if not path.is_file():
            ap.error(f"missing source prerequisite: {path}")
    # Stage only the known ADC-channel extension; dependency sources stay intact.
    import importlib.util
    spec = importlib.util.spec_from_file_location("switch_io_patch", Path(__file__).with_name("patch_runtime_io.py"))
    patcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(patcher)
    spec = importlib.util.spec_from_file_location("switch_perf_patch", Path(__file__).with_name("patch_runtime_perf.py"))
    perf_patcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(perf_patcher)
    staged_src = obj / "runtime-src"
    perf_patcher.stage_runtime(src, staged_src, patcher.microphone_source, args.minimal_profiling)
    includes.insert(0, staged_src)
    units = [(staged_src / path.name if path.parent == src else path, name, bank)
             for path, name, bank in units]

    # Conservative header-content key: a changed ABI or generated header must
    # invalidate cached objects, not just a changed .cpp modification time.
    header_hash = hashlib.sha256()
    for directory in includes:
        for p in sorted(directory.rglob("*")):
            if p.is_file() and p.suffix in (".h", ".hpp", ".inl"):
                header_hash.update(p.as_posix().encode())
                header_hash.update(p.read_bytes())
    headers_key = header_hash.digest()
    arch = ["-march=armv8-a+crc+crypto", "-mtune=cortex-a57", "-mtp=soft", "-fPIE"]
    common = ["-ffunction-sections", "-fdata-sections", *arch,
              "-D__SWITCH__", "-DNDS_SWITCH=1", '-DMELONDS_GL_HEADER="melonds_gl_stub.hpp"',
              f"-DVORE_PRIVATE_BANKS={int(banks is not None)}", "-Wno-unused-parameter"]
    if args.minimal_profiling: common += ["-DVORE_MINIMAL_PROFILING=1"]
    for p in includes:
        common += ["-I", p.as_posix()]

    def compile_unit(unit):
        path, name, bank = unit
        target = obj / f"{name}.o"
        stamp = obj / f"{name}.sha256"
        c = path.suffix == ".c"
        big = bank and path.stat().st_size >= BIG_BYTES
        lean_giant = big and not args.bank_lto
        flags = ["-O1" if lean_giant else "-" + args.optimization, *common]
        if args.lto and (not bank or args.bank_lto):
            flags += [f"-flto={args.jobs}"]
            if args.bank_lto: flags += ["-fno-fat-lto-objects"]
        if c:
            flags += ["-std=gnu11"]
            parts = path.stem.split("_")
            if ("arm9" in parts) != ("arm7" in parts):
                flags += [f"-DNDS_STATIC_CPU={0 if 'arm9' in parts else 1}"]
            elif bank:
                raise ValueError(f"cannot infer a unique bank CPU: {path.name}")
        else:
            flags += ["-g", "-std=gnu++20", "-frtti", "-fno-exceptions",
                      "-Wno-unused-variable", "-Wno-sign-compare",
                      "-Wno-missing-field-initializers"]
        command = [str(gcc if c else gxx), *flags, "-c", path.as_posix()]
        key = hashlib.sha256(headers_key + repr(command).encode() + path.read_bytes()).hexdigest()
        if target.is_file() and target.stat().st_size > 0 and stamp.is_file():
            if stamp.read_text() == key:
                return target
        temp = target.with_suffix(".o.tmp")
        log = obj / f"{name}.log"
        print(f"compile {name} ({'-O1 serial' if lean_giant else '-' + args.optimization})", flush=True)
        with log.open("w") as f:
            subprocess.run(command + ["-o", temp.as_posix()], env=env,
                           stdout=f, stderr=subprocess.STDOUT, check=True)
        # A cancelled/failed compiler can never leave a fresh-looking cache hit.
        temp.replace(target)
        stamp.write_text(key)
        return target

    giants = [u for u in units if u[2] and u[0].stat().st_size >= BIG_BYTES]
    small = [u for u in units if u not in giants]
    objects = [compile_unit(u) for u in giants]
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        objects += list(pool.map(compile_unit, small))
    if args.runtime_only:
        print(f"Compiled {len(objects)} runtime/registry objects in {obj}; no bank objects linked")
        return

    name = "vore-nx-private" if banks else "vore-nx-interpreter"
    elf, nro, nacp = (out / f"{name}.{ext}" for ext in ("elf", "nro", "nacp"))
    # Exact object list: old banks in the output directory are never glob-linked.
    response = obj / "link.rsp"
    link_args = [*arch, *(p.as_posix() for p in objects),
                 f"-specs={(dkp / 'libnx/switch.specs').as_posix()}",
                 f"-Wl,-Map,{(obj / 'runtime.map').as_posix()}",
                 f"-L{(dkp / 'libnx/lib').as_posix()}", "-lnx", "-o", elf.as_posix()]
    if args.lto: link_args[:0] = [f"-flto={args.jobs}", "-" + args.optimization]
    if args.bank_lto: link_args[:0] = ["-Werror=lto-type-mismatch"]
    response.write_text("\n".join('"' + a.replace('"', '\\"') + '"' for a in link_args))
    subprocess.run([str(gxx), "@" + response.as_posix()], env=env, check=True)
    subprocess.run([str(dkp / ("tools/bin/nacptool" + suffix)), "--create",
                    name, "vore-nx-dev", "0.2.0", str(nacp)], env=env, check=True)
    subprocess.run([str(dkp / ("tools/bin/elf2nro" + suffix)), str(elf), str(nro),
                    "--nacp=" + str(nacp)], env=env, check=True)
    print(f"Built {nro}; {'ROM-DERIVED: DO NOT DISTRIBUTE' if banks else 'experimental, not a release'}")


if __name__ == "__main__":
    main()
