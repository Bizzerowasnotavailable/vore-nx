#!/usr/bin/env python3
"""Offline AOT preparation for European CLJP revision 0; private outputs only."""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
from bootstrap_host import (CORE_COMMIT, NDS_COMMIT, NDSPY_SHA256,
                            NDSPY_VERSION, WORK, digest)

REPO = Path(__file__).resolve().parents[1]
WORKSPACE = REPO.parent
SUPPORTED_SHA256 = "4d8a3ffa13ad525db85e596d576675860a816aa77560ca87c4505451c172c60b"
EDITION = "European CLJP revision 0"
SDK_MAGIC = struct.pack("<II", 0xDEC00621, 0x2106C0DE)
DEFAULT_OUT = REPO / "private/aot" / SUPPORTED_SHA256
DEFAULT_NDSPY = WORK / "downloads/ndspy-4.2.0-py3-none-any.whl"
DEFAULT_RECOMPILER = WORK / "recompiler-build-direct/nds_recompile.exe"
DEFAULT_SOURCE = WORK / "sources" / f"ndsrecomp-{NDS_COMMIT}"
RUNTIME_HEADER_PINS = {
    "recompiler/armv4t/runtime_arm.h": "4a65705ff481078163203c23f2a32eccf973d0bc628a6903ef64146cf78e0272",
    "external/arm-recomp-core/common/runtime_arm_types.h": "b356fc36d3be43691505fbe7b2fdcfcd178c443dcbd63464da8daabba007c356",
}


def private_path(path, repo=REPO, workspace=WORKSPACE):
    """Resolve existing symlinks/junctions before allowing any output."""
    resolved = Path(path).resolve()
    roots = ((Path(repo) / "private").resolve(),
             (Path(workspace) / "local-work").resolve())
    # Also reject roots that are themselves redirects out of the intended tree.
    lexical = (Path(repo).resolve() / "private", Path(workspace).resolve() / "local-work")
    if not any(root == expected and resolved.is_relative_to(root)
               and resolved != root for root, expected in zip(roots, lexical)):
        raise ValueError("Output must be below repo/private/ or workspace/local-work/ (no escaping links)")
    return resolved


def write_private(path, data, *, same_only=False):
    path = private_path(path)
    if path.exists() and same_only:
        if path.read_bytes() != data:
            raise ValueError(f"Existing prepared output differs; choose a new --out: {path.name}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def verify_rom(path):
    """Hash an immutable in-memory snapshot before creating ANY output."""
    path = Path(path)
    size = path.stat().st_size
    if not 512 <= size <= 512 * 1024 * 1024:
        raise ValueError("Unsupported cartridge size")
    with path.open("rb") as stream:
        data = stream.read(512 * 1024 * 1024 + 1)
    if len(data) != size or hashlib.sha256(data).hexdigest() != SUPPORTED_SHA256:
        raise ValueError("Unsupported ROM SHA256; no preparation outputs written")
    if data[12:16] != b"CLJP" or data[0x1e] != 0 or data[0x12] != 0:
        raise ValueError(f"Expected original-DS {EDITION}")
    if crc16(data[:0x15e]) != struct.unpack_from("<H", data, 0x15e)[0]:
        raise ValueError("Invalid header CRC16")
    return data


def crc16(data):
    result = 0xffff
    for byte in data:
        result ^= byte
        for _ in range(8):
            result = (result >> 1) ^ (0xa001 if result & 1 else 0)
    return result


def region(data, offset, size):
    if offset < 0 or size < 0 or offset + size > len(data):
        raise ValueError("Cartridge range outside verified snapshot")
    return data[offset:offset + size]


def cartridge_metadata(data):
    mains = []
    for cpu, offset in ((9, 0x20), (7, 0x30)):
        rom_offset, entry, load, size = struct.unpack_from("<4I", data, offset)
        end = load + size
        valid_ram = 0x02000000 <= load < end <= 0x02400000
        if cpu == 7:
            valid_ram |= 0x037f8000 <= load < end <= 0x03810000
        if (rom_offset < 512 or not size or size % 4 or not valid_ram
                or not load <= (entry & ~1) < end
                or (entry & ~1) % (2 if entry & 1 else 4)):
            raise ValueError("Invalid main image load/entry/range")
        region(data, rom_offset, size)
        mains.append(dict(cpu=cpu, rom_offset=rom_offset, entry=entry, load=load, raw_size=size))
    fat_offset, fat_size = struct.unpack_from("<2I", data, 0x48)
    if fat_size % 8 or fat_size > 2 * 1024 * 1024:
        raise ValueError("Invalid FAT")
    fat = list(struct.iter_unpack("<2I", region(data, fat_offset, fat_size)))
    for begin, end in fat:
        if end < begin:
            raise ValueError("Backwards FAT range")
        region(data, begin, end - begin)
    overlays = []
    for cpu, offset in ((9, 0x50), (7, 0x58)):
        start, length = struct.unpack_from("<2I", data, offset)
        if length % 32 or length > 2 * 1024 * 1024:
            raise ValueError("Invalid overlay table")
        seen = set()
        for row in struct.iter_unpack("<8I", region(data, start, length)):
            ident, load, size, bss, init_start, init_end, file_id, flags_size = row
            if ident in seen or file_id >= len(fat) or load + size + bss > 0x100000000:
                raise ValueError("Invalid overlay descriptor")
            seen.add(ident)
            begin, end = fat[file_id]
            overlays.append(dict(cpu=cpu, id=ident, load_address=load, size=size,
                                 bss_size=bss, static_init_start=init_start,
                                 static_init_end=init_end, file_id=file_id,
                                 rom_offset=begin, raw_size=end - begin,
                                 compressed_in_rom=bool(flags_size & 0x01000000),
                                 compressed_size=flags_size & 0xffffff,
                                 flags=flags_size >> 24,
                                 translation="metadata-only; no entry seeds"))
    return mains, overlays


def sdk_settings(data):
    matches = [i for i in range(28, min(len(data) - 7, 0x8000), 4)
               if data[i:i + 8] == SDK_MAGIC]
    if len(matches) > 1:
        raise ValueError("Ambiguous SDK module parameters")
    if not matches:
        return None
    offset = matches[0] - 28
    words = struct.unpack_from("<7I", data, offset)
    return dict(offset=offset, magic_offset=matches[0],
                autoload_start=words[0], autoload_end=words[1],
                autoload_data=words[2], bss_start=words[3], bss_end=words[4],
                compressed_static_end=words[5], sdk_version=words[6])


def compression_footer(raw):
    """Strict end-of-image BLZ footer evidence; no appended-data guessing."""
    if len(raw) < 8:
        return None
    packed, extra = struct.unpack_from("<2I", raw, len(raw) - 8)
    header = packed >> 24
    compressed = packed & 0xffffff
    if not (extra and 8 <= header <= compressed <= len(raw)):
        return None
    if any(byte != 0xff for byte in raw[len(raw) - header:len(raw) - 8]):
        return None
    return dict(header_bytes=header, compressed_bytes=compressed,
                extra_bytes=extra, passthrough_bytes=len(raw) - compressed,
                expected_size=len(raw) + extra)


def load_decompressor(wheel):
    wheel = Path(wheel).resolve()
    if not wheel.is_file():
        raise ValueError("Pinned ndspy is absent. Explicitly run tools/bootstrap_host.py ndspy, or use --raw-startup-only")
    if digest(wheel) != NDSPY_SHA256:
        raise ValueError("ndspy wheel SHA256 mismatch")
    # Never silently use a globally installed/preloaded library.
    for name in tuple(sys.modules):
        if name == "ndspy" or name.startswith("ndspy."):
            origin = str(getattr(sys.modules[name], "__file__", ""))
            if not origin.startswith(str(wheel) + os.sep):
                raise ValueError("Another ndspy is already loaded; use a clean Python process")
    sys.path.insert(0, str(wheel))
    try:
        module = importlib.import_module("ndspy.codeCompression")
        if not str(module.__file__).startswith(str(wheel) + os.sep):
            raise ValueError("ndspy did not load from the verified wheel")
        return module.decompress
    finally:
        sys.path.pop(0)


def autoload_copies(image, load, settings):
    if not settings:
        return []
    start, end = settings["autoload_start"], settings["autoload_end"]
    source = settings["autoload_data"]
    if not (load <= source <= start <= end <= load + len(image)) or (end - start) % 12:
        raise ValueError("SDK autoload table is inconsistent with expanded image")
    copies = []
    for destination, size, bss in struct.iter_unpack("<3I", image[start - load:end - load]):
        if source + size > start or destination + size + bss > 0x100000000:
            raise ValueError("Invalid SDK autoload copy")
        if size:
            copies.append(dict(runtime_start=destination, source_start=source,
                               size=size, bss_size=bss))
        source += size
    return copies


def prepare_main(raw, meta, wheel, raw_only=False):
    settings = sdk_settings(raw)
    footer = compression_footer(raw)
    sdk_compressed = bool(settings and settings["compressed_static_end"])
    evidence = dict(sdk=settings, footer=footer, ndspy_version=None,
                    mode="raw-no-code-compression-evidence", coverage="main CFG only; not complete coverage")
    prepared = raw
    excluded = []
    copies = []
    bounded_entry = False
    if sdk_compressed and settings["compressed_static_end"] != meta["load"] + len(raw):
        if not raw_only:
            raise ValueError("SDK compressed end does not match raw image; use --raw-startup-only")
        bounded_entry = True
    if sdk_compressed or footer:
        if raw_only:
            evidence["mode"] = "raw-startup-only"
            evidence["coverage"] = "raw startup prefix only; compressed executable body NOT translated"
            if footer and not bounded_entry:
                excluded = [(meta["load"] + footer["passthrough_bytes"], meta["load"] + len(raw))]
            else:
                bounded_entry = True
        else:
            if not footer or footer["expected_size"] > 16 * 1024 * 1024:
                raise ValueError("Compression cannot be demonstrated safely; use --raw-startup-only")
            if meta["load"] + footer["expected_size"] > 0x02400000:
                raise ValueError("Expanded image would exceed main RAM")
            prepared = bytes(load_decompressor(wheel)(raw))
            prefix = footer["passthrough_bytes"]
            if len(prepared) != footer["expected_size"] or prepared[:prefix] != raw[:prefix]:
                raise ValueError("Decompressor disagrees with footer size/passthrough evidence")
            if settings and sdk_settings(prepared) != settings:
                raise ValueError("Decompression changed SDK parameters")
            copies = autoload_copies(prepared, meta["load"], settings)
            if settings and settings["autoload_end"] != meta["load"] + len(prepared):
                raise ValueError("Expanded size does not match SDK autoload-table end; use --raw-startup-only")
            evidence.update(mode="expanded-code-compression", ndspy_version=NDSPY_VERSION,
                            ndspy_wheel_sha256=NDSPY_SHA256,
                            coverage="expanded main CFG and declared SDK copies; overlays excluded",
                            byte_policy="expanded bytes unchanged; SDK compressed-end word NOT patched",
                            relocation_scan="disabled: expanded analysis input must not run startup decompression twice")
    elif settings:
        copies = autoload_copies(prepared, meta["load"], settings)
    if bounded_entry:
        evidence["coverage"] = "one explicitly bounded startup instruction only; compression uncertain"
    if any(start <= (meta["entry"] & ~1) < end for start, end in excluded):
        raise ValueError("Entry lies inside compressed payload; cannot emit raw startup bank")
    result = dict(meta, prepared_size=len(prepared), raw_sha1=hashlib.sha1(raw).hexdigest(),
                  raw_sha256=hashlib.sha256(raw).hexdigest(),
                  prepared_sha1=hashlib.sha1(prepared).hexdigest(),
                  prepared_sha256=hashlib.sha256(prepared).hexdigest(),
                  compression=evidence, code_copies=copies)
    return prepared, result, excluded, bounded_entry


def config_text(meta, excluded=(), bounded_entry=False):
    entry = meta["entry"] & ~1
    mode = "thumb" if meta["entry"] & 1 else "arm"
    lines = ["# Private analysis input; do not commit.", "[program]",
             f'name = "BIS ARM{meta["cpu"]} main"',
             f'load_address = 0x{meta["load"]:08X}',
             f'size = {meta["prepared_size"]}', f"entry_pc = 0x{entry:08X}"]
    if bounded_entry:
        lines.append("authoritative_entry_points = true")
    lines += ["", "[identity]", f'sha1 = "{meta["prepared_sha1"]}"']
    if mode == "thumb" or bounded_entry:
        lines += ["", "[[entry_point]]", f"addr = 0x{entry:08X}", f'mode = "{mode}"']
        if bounded_entry:
            lines.append(f'size = {2 if mode == "thumb" else 4}')
    for start, end in excluded:
        lines += ["", "[[data_range]]", f"start = 0x{start:08X}", f"end = 0x{end:08X}",
                  'note = "compressed payload: not executable analysis bytes"']
    for copy in meta["code_copies"]:
        lines += ["", "[[code_copy]]", f'runtime_start = 0x{copy["runtime_start"]:08X}',
                  f'source_start = 0x{copy["source_start"]:08X}', f'size = {copy["size"]}',
                  'note = "SDK autoload descriptor; readability alias, not a guessed entry seed"']
    return "\n".join(lines) + "\n"


def prepare(rom, out, wheel=DEFAULT_NDSPY, raw_only=False):
    snapshot = verify_rom(rom)  # Must precede every mkdir/write.
    out = private_path(out)
    mains, overlays = cartridge_metadata(snapshot)
    outputs = {}
    records = []
    for meta in mains:
        raw = region(snapshot, meta["rom_offset"], meta["raw_size"])
        image, record, excluded, bounded = prepare_main(raw, meta, wheel, raw_only)
        stem = f'arm{meta["cpu"]}'
        outputs[f"inputs/{stem}.raw.bin"] = raw
        outputs[f"inputs/{stem}.bin"] = image
        outputs[f"inputs/{stem}.toml"] = config_text(record, excluded, bounded).encode()
        records.append(record)
    outputs["overlays.json"] = json_bytes(dict(policy="metadata only; never seed load addresses", overlays=overlays))
    manifest = dict(schema=1, rom_sha256=SUPPORTED_SHA256, code="CLJP", revision=0,
                    ndsrecomp_commit=NDS_COMMIT, arm_core_commit=CORE_COMMIT,
                    mains=records, overlay_counts={str(cpu): sum(x["cpu"] == cpu for x in overlays) for cpu in (9, 7)},
                    files={name: hashlib.sha256(data).hexdigest() for name, data in outputs.items()},
                    limitation="Preparation is not a playable port or complete static coverage")
    outputs["manifest.json"] = json_bytes(manifest)
    # Compute/validate everything before the first output; never replace differing inputs.
    for name, data in outputs.items():
        target = private_path(out / name)
        if target.exists() and target.read_bytes() != data:
            raise ValueError(f"Existing output differs; choose a new --out: {name}")
    for name, data in outputs.items():
        write_private(out / name, data, same_only=True)
    return manifest


def run(command, *, env=None):
    result = subprocess.run([str(x) for x in command], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", env=env, timeout=900)
    text = result.stdout + result.stderr
    if result.returncode:
        raise ValueError(f"Command failed ({result.returncode}): {Path(command[0]).name}\n{text[-6000:]}")
    return text


def recompiler_environment(meta):
    env = os.environ.copy()
    # Do not inherit an accidental opt-out from another development session.
    env.pop("NDSRECOMP_NO_RELOC_SCAN", None)
    if meta["compression"]["mode"] == "expanded-code-compression":
        env["NDSRECOMP_NO_RELOC_SCAN"] = "1"
    return env


def verify_generated(directory, bank):
    directory = Path(directory)
    header = directory / f"{bank}.h"
    dispatch = directory / f"{bank}_dispatch.c"
    bodies = sorted(directory.glob(f"{bank}_[0-9][0-9].c"))
    if not header.is_file() or not dispatch.is_file() or not bodies or len(bodies) > 2:
        raise ValueError(f"Missing generated header/body/dispatch for {bank}")
    files = [header, dispatch] + bodies
    if any(not item.stat().st_size for item in files):
        raise ValueError("Empty generated output")
    table = dispatch.read_text(encoding="utf-8")
    if (f"const NdsDispatchEntry g_dispatch_{bank}[]" not in table
            or not re.search(rf"g_dispatch_{re.escape(bank)}_len\s*=\s*[1-9][0-9]*", table)
            or "static const NdsStaticValidation " not in table):
        raise ValueError("Generated dispatch is empty, incomplete, or lacks live-byte validation")
    declared = int(re.search(rf"g_dispatch_{re.escape(bank)}_len\s*=\s*([1-9][0-9]*)", table)[1])
    rows = re.findall(r"^\s*\{0x[0-9A-Fa-f]+u, [01]u, [A-Za-z_][A-Za-z_0-9]*, &g_validation_", table, re.MULTILINE)
    if len(rows) != declared:
        raise ValueError("Generated dispatch row count/validation does not match its declared length")
    if not all(bank + "_" in body.read_text(encoding="utf-8") for body in bodies):
        raise ValueError("Generated body does not define the requested bank")
    return {item.name: dict(bytes=item.stat().st_size, sha256=digest(item)) for item in files}


def translate(manifest, out, recompiler, generate=False):
    out = private_path(out)
    recompiler = Path(recompiler).resolve()
    identity = run([recompiler, "--codegen-identity"]).strip()
    if identity != "nds-codegen-v3":
        raise ValueError(f"Unexpected recompiler codegen identity: {identity}")
    results = dict(recompiler_sha256=digest(recompiler), codegen_identity=identity, banks={})
    for meta in manifest["mains"]:
        cpu = meta["cpu"]
        bank = f"bis_arm{cpu}_main"
        base = [recompiler, "--config", out / f"inputs/arm{cpu}.toml", "--bin", out / f"inputs/arm{cpu}.bin"]
        command = base + ["--audit"]
        if generate:
            stage_parent = private_path(out / ".staging")
            stage_parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix=bank + "-", dir=stage_parent) as temporary:
                command = base + ["--out", temporary, "--bank", bank, "--shards", "2", "--validate-live-bytes"]
                text = run(command, env=recompiler_environment(meta))
                files = verify_generated(temporary, bank)
                destination = private_path(out / "generated" / bank)
                if destination.exists():
                    if verify_generated(destination, bank) != files:
                        raise ValueError("Existing generated bank differs; choose a new --out")
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(temporary, destination)
        else:
            text = run(command, env=recompiler_environment(meta))
            files = {}
        kind = "generate" if generate else "audit"
        write_private(out / "logs" / f"{bank}.{kind}.log", text.encode())
        found = re.search(r"\[finder\] functions=(\d+) \(arm=(\d+) thumb=(\d+)\)", text)
        if not found or int(found[1]) == 0:
            raise ValueError(f"No discovered functions for {bank}; see private log")
        outcomes = re.search(r"indirect outcomes \(non-return\): resolved=(\d+) known-unreachable=(\d+) unknown=(\d+)", text)
        results["banks"][bank] = dict(functions=int(found[1]), arm=int(found[2]), thumb=int(found[3]),
                                     files=files, relocation_scan="disabled" if meta["compression"]["mode"] == "expanded-code-compression" else "enabled",
                                     indirect_outcomes=dict(zip(("resolved", "known_unreachable", "unknown"), map(int, outcomes.groups()))) if outcomes else None)
    write_private(out / ("generation.json" if generate else "audit.json"), json_bytes(results))
    return results


def smoke_objects(out, compiler, source):
    out = private_path(out)
    source = Path(source).resolve()
    includes = [source / "recompiler/armv4t", source / "external/arm-recomp-core/common",
                source / "external/arm-recomp-core/profiles/armv5te_nds"]
    if not (includes[1] / "runtime_arm_types.h").is_file():
        raise ValueError("Matching runtime_arm_types.h missing; bootstrap host dependencies")
    for name, expected in RUNTIME_HEADER_PINS.items():
        if digest(source / name) != expected:
            raise ValueError(f"Runtime ABI header differs from the pinned source: {name}")
    result = dict(compiler=run([compiler, "--version"]).splitlines()[0],
                  target=run([compiler, "-dumpmachine"]).strip(),
                  runtime_headers=RUNTIME_HEADER_PINS, objects={})
    if result["target"] != "aarch64-none-elf":
        raise ValueError("Smoke compiler must target aarch64-none-elf")
    for cpu in (9, 7):
        bank = f"bis_arm{cpu}_main"
        directory = out / "generated" / bank
        files = verify_generated(directory, bank)
        for filename in files:
            if not filename.endswith(".c"):
                continue
            src = directory / filename
            obj = private_path(out / "objects" / (filename + ".o"))
            obj.parent.mkdir(parents=True, exist_ok=True)
            command = [compiler, "-std=gnu11", "-O0", "-g0", f"-DNDS_STATIC_CPU={0 if cpu == 9 else 1}"]
            for include in includes:
                command += ["-I", include]
            command += ["-I", directory, "-c", src, "-o", obj]
            log = run(command)
            write_private(out / "logs" / (filename + ".compile.log"), log.encode())
            if not obj.is_file() or obj.stat().st_size < 64:
                raise ValueError("Compiler returned without a nonempty object")
            # ELF64 little-endian, relocatable, AArch64 (183).
            header = obj.read_bytes()[:64]
            if header[:6] != b"\x7fELF\x02\x01" or struct.unpack_from("<HH", header, 16) != (1, 183):
                raise ValueError("Smoke output is not an AArch64 relocatable object")
            result["objects"][obj.name] = dict(bytes=obj.stat().st_size, sha256=digest(obj))
    write_private(out / "object-smoke.json", json_bytes(result))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "config", "audit", "generate", "smoke"),
                        help="config is an alias for prepare; both write identity-checked configs")
    parser.add_argument("--rom", type=Path, default=WORKSPACE / "rom.nds")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--ndspy-wheel", type=Path, default=DEFAULT_NDSPY)
    parser.add_argument("--raw-startup-only", action="store_true", help="explicitly omit compressed main code")
    parser.add_argument("--recompiler", type=Path, default=DEFAULT_RECOMPILER)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--cc", type=Path, help="devkitA64 aarch64-none-elf-gcc executable (smoke only)")
    args = parser.parse_args(argv)
    try:
        manifest = prepare(args.rom, args.out, args.ndspy_wheel, args.raw_startup_only)
        if args.command in ("audit", "generate"):
            result = translate(manifest, args.out, args.recompiler, args.command == "generate")
        elif args.command == "smoke":
            if not args.cc:
                raise ValueError("smoke requires explicit --cc; this is not a runtime/link test")
            result = smoke_objects(args.out, args.cc, args.source)
        else:
            result = dict(rom_sha256=manifest["rom_sha256"], overlay_counts=manifest["overlay_counts"],
                          mains=[dict(cpu=m["cpu"], raw_size=m["raw_size"], prepared_size=m["prepared_size"],
                                      mode=m["compression"]["mode"]) for m in manifest["mains"]])
        print(json.dumps(dict(edition=EDITION, **result), indent=2))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"AOT refused/failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
