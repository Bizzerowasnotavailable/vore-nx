#!/usr/bin/env python3
"""Turn coverage-derived seeds into generated, content-validated static banks.

This is the missing overlay stage of the ndsrecomp pipeline, wired up for one
specific cartridge:

    coverage manifest  ->  ingest_coverage_manifests.py  ->  per-module seeds
                       ->  this script  ->  nds_recompile  ->  *_dispatch.c

Banks are emitted flat with a `_arm9_`/`_arm7_` name segment because the runner
CMake infers the CPU from the source name.

Private tooling: every input and output here is ROM-derived. Nothing produced
by this script may be committed or published.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCAL = Path(os.environ.get("VORE_WORK") or HERE.parent).resolve()
WORKSPACE = LOCAL.parent
RECOMPILER = LOCAL / "recompiler-build-direct" / "nds_recompile.exe"
IMAGES = LOCAL / "analysis-images"
INGEST = LOCAL / "coverage" / "ingest"  # replaced by --ingest when staging
AOT = (Path(os.environ.get("VORE_AOT") or
            WORKSPACE / "vore-nx" / "private" / "aot"
            / "4d8a3ffa13ad525db85e596d576675860a816aa77560ca87c4505451c172c60b"))
OUT = LOCAL / "banks"
CONFIGS = LOCAL / "banks-configs"
ROM_SHA1 = "5f35bfbf79a0947740795dd770d99e8eea3ac85e"


def read_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def emit_config(path: Path, *, name: str, load: int, size: int, entry: int,
                sha1: str, seeds: list[dict], code_copies=(), data_ranges=(),
                rom_sha1: str | None = ROM_SHA1, authoritative=False) -> None:
    lines = [
        f"# Private generated analysis config for {name}; do not commit.",
        "[program]",
        f'name = "{name}"',
        f'id = "{name}"',
        f"load_address = 0x{load:08X}",
        f"size = {size}",
        f"entry_pc = 0x{entry:08X}",
    ]
    if authoritative:
        lines.append("authoritative_entry_points = true")
    lines += ["", "[identity]", f'sha1 = "{sha1}"']
    if rom_sha1:
        lines.append(f'rom_sha1 = "{rom_sha1}"')
    for copy in code_copies:
        lines += ["", "[[code_copy]]",
                  f'runtime_start = 0x{copy["runtime_start"]:08X}',
                  f'source_start = 0x{copy["source_start"]:08X}',
                  f'size = {copy["size"]}',
                  'note = "SDK autoload alias from the main-image config"']
    for start, end in data_ranges:
        lines += ["", "[[data_range]]", f"start = 0x{start:08X}",
                  f"end = 0x{end:08X}", 'note = "declared non-code range"']
    for seed in seeds:
        lines += ["", "[[entry_point]]", f'addr = 0x{seed["addr"]:08X}',
                  f'mode = "{seed["mode"]}"', 'kind = "runtime_observed"']
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def seeds_from(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    doc = read_toml(path)
    out = []
    for ep in doc.get("entry_point", []):
        out.append(dict(addr=int(ep["addr"]), mode=str(ep.get("mode", "arm"))))
    return out


def seeds_from_manifest(manifest: dict) -> list[dict]:
    out = []
    for ep in manifest.get("entry_point", []):
        out.append(dict(addr=int(ep["addr"]), mode=str(ep.get("mode", "arm"))))
    return out


def run_recompiler(config: Path, binary: Path, bank: str, out_dir: Path,
                   reloc_scan: bool = False, shards: int = 2) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    # The relocation scan proves copy aliases inside one image. It is what
    # lets the ARM7 main image reach its own relocated copies, and it is
    # noise for an overlay that is loaded verbatim at a known base.
    env.pop("NDSRECOMP_NO_RELOC_SCAN", None)
    if not reloc_scan:
        env["NDSRECOMP_NO_RELOC_SCAN"] = "1"
    with tempfile.TemporaryDirectory(prefix=bank + "-", dir=out_dir) as tmp:
        cmd = [str(RECOMPILER), "--config", str(config), "--bin", str(binary),
               "--out", tmp, "--bank", bank, "--shards", str(shards),
               "--validate-live-bytes"]
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=env,
                              timeout=3600)
        text = proc.stdout + proc.stderr
        if proc.returncode:
            raise RuntimeError(f"{bank}: recompiler failed\n{text[-4000:]}")
        (CONFIGS / f"{bank}.log").write_text(text, encoding="utf-8")
        files = sorted(Path(tmp).glob("*"))
        if not files:
            raise RuntimeError(f"{bank}: no output")
        destination = out_dir / bank
        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(parents=True)
        for item in files:
            shutil.move(str(item), str(destination / item.name))
    dispatch = (destination / f"{bank}_dispatch.c").read_text(encoding="utf-8")
    if "NdsStaticValidation" not in dispatch:
        raise RuntimeError(f"{bank}: dispatch has no live-byte validation")
    return dict(bank=bank, functions=text.count("runtime_enter_"),
                dispatch_bytes=len(dispatch))


def main() -> int:
    global INGEST
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--only", nargs="*", default=None,
                    help="limit to these bank names")
    ap.add_argument("--skip-main", action="store_true")
    ap.add_argument("--skip-coverage", action="store_true")
    ap.add_argument("--ingest", type=Path, default=INGEST,
                    help="ingest output directory holding seeds/ and images/")
    args = ap.parse_args()

    if not RECOMPILER.is_file():
        raise SystemExit(f"missing recompiler: {RECOMPILER}")
    INGEST = args.ingest.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    CONFIGS.mkdir(parents=True, exist_ok=True)

    overlays = {Path(r["file"]).stem: r for r in
                json.loads((IMAGES / "overlays.json").read_text(encoding="utf-8"))}
    jobs = []

    # 1. Main images re-seeded with everything the interpreter saw there.
    if not args.skip_main:
        main9 = read_toml(AOT / "inputs" / "arm9.toml")
        jobs.append(dict(
            bank="bis_arm9_main", binary=AOT / "inputs" / "arm9.bin",
            name="BIS ARM9 main (coverage re-seed)",
            load=main9["program"]["load_address"], size=main9["program"]["size"],
            entry=main9["program"]["entry_pc"],
            sha1=hashlib.sha1((AOT / "inputs" / "arm9.bin").read_bytes()).hexdigest(),
            seeds=seeds_from(INGEST / "seeds" / "arm9_arm9_02004000.toml"),
            code_copies=main9.get("code_copy", [])))
        main7 = read_toml(AOT / "inputs" / "arm7.toml")
        jobs.append(dict(
            bank="bis_arm7_main", binary=AOT / "inputs" / "arm7.bin",
            name="BIS ARM7 main (coverage re-seed)",
            load=main7["program"]["load_address"], size=main7["program"]["size"],
            entry=main7["program"]["entry_pc"],
            sha1=hashlib.sha1((AOT / "inputs" / "arm7.bin").read_bytes()).hexdigest(),
            seeds=seeds_from(INGEST / "seeds" / "arm7_arm7_02380000.toml"),
            code_copies=main7.get("code_copy", []), reloc_scan=True))

    # 2. Overlay banks: the ROM image recompiled at its own load address.
    for stem, record in sorted(overlays.items()):
        seed_path = INGEST / "seeds" / f"arm9_{stem}_{int(record['load_address'], 16):08x}.toml"
        seeds = seeds_from(seed_path)
        if not seeds:
            continue
        binary = IMAGES / "overlays" / record["file"]
        jobs.append(dict(
            bank=f"bis_{stem}_arm9", binary=binary,
            name=f"BIS overlay {record['overlay_id']} at {record['load_address']}",
            load=int(record["load_address"], 16), size=int(record["size"]),
            entry=min(s["addr"] for s in seeds),
            sha1=hashlib.sha1(binary.read_bytes()).hexdigest(),
            seeds=seeds))

    # 3. Relocated main-image aliases (the module running from a second base).
    for seeds_name, bank in (("arm7_arm7_037f7de4", "bis_arm7_alias_037f7de4"),
                             ("arm7_arm7_027d076c", "bis_arm7_alias_027d076c")):
        seeds = seeds_from(INGEST / "seeds" / f"{seeds_name}.toml")
        if not seeds:
            continue
        load = int(seeds_name.split("_")[-1], 16)
        jobs.append(dict(
            bank=bank, binary=AOT / "inputs" / "arm7.bin",
            name=f"BIS ARM7 image resident at 0x{load:08X}",
            load=load, size=(AOT / "inputs" / "arm7.bin").stat().st_size,
            entry=min(s["addr"] for s in seeds),
            sha1=hashlib.sha1((AOT / "inputs" / "arm7.bin").read_bytes()).hexdigest(),
            seeds=seeds))

    # 4. The 35 runtime-materialized banks ingest already assembled.
    if not args.skip_coverage:
        for toml_path in sorted((INGEST / "images").glob("*.toml")):
            doc = read_toml(toml_path)
            binary = INGEST / "images" / (toml_path.stem + ".bin")
            if not binary.is_file():
                continue
            jobs.append(dict(
                bank=toml_path.stem, binary=binary,
                name=doc["program"]["name"],
                load=doc["program"]["load_address"],
                size=doc["program"]["size"],
                entry=doc["program"]["entry_pc"],
                sha1=doc["identity"]["sha1"],
                seeds=seeds_from_manifest(doc)))

    if args.only:
        wanted = set(args.only)
        jobs = [j for j in jobs if j["bank"] in wanted]

    print(f"building {len(jobs)} banks")
    results = []
    for index, job in enumerate(jobs, 1):
        config = CONFIGS / f"{job['bank']}.toml"
        emit_config(config, name=job["name"], load=job["load"], size=job["size"],
                    entry=job["entry"], sha1=job["sha1"], seeds=job["seeds"],
                    code_copies=job.get("code_copies", ()))
        try:
            result = run_recompiler(config, job["binary"], job["bank"], args.out,
                                    reloc_scan=job.get("reloc_scan", False))
        except (RuntimeError, subprocess.SubprocessError) as error:
            print(f"[{index}/{len(jobs)}] {job['bank']}: FAILED {error}")
            results.append(dict(bank=job["bank"], ok=False, error=str(error)))
            continue
        result["ok"] = True
        result["seeds"] = len(job["seeds"])
        results.append(result)
        print(f"[{index}/{len(jobs)}] {job['bank']}: seeds={len(job['seeds'])} "
              f"dispatch={result['dispatch_bytes']}B")

    summary = dict(banks=len(results), failed=[r["bank"] for r in results if not r["ok"]],
                   results=results)
    (CONFIGS / "build-report.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(dict(banks=len(results), failed=summary["failed"]), indent=2))
    return 0 if not summary["failed"] else 1


if __name__ == "__main__":
    sys.exit(main())
