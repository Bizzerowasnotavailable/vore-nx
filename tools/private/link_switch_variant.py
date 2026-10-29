#!/usr/bin/env python3
"""Link an explicitly inventoried, private bank-compiler experiment with libnx."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def bank_objects(banks, objects, validator):
    sources = sorted(banks.glob("*.c"))
    if not sources: raise ValueError("empty generated-bank directory")
    result, abi_keys = [], set()
    for source in sources:
        obj = objects / ("bank_" + source.stem + ".o")
        metadata = json.loads(obj.with_suffix(".json").read_text())
        if metadata["source_sha256"] != hashlib.sha256(source.read_bytes()).hexdigest():
            raise ValueError(f"bank object does not match source: {source.name}")
        if "static_cpu" in metadata:
            parts = source.stem.split("_")
            expected = 0 if "arm9" in parts and "arm7" not in parts else (
                1 if "arm7" in parts and "arm9" not in parts else None)
            if type(metadata["static_cpu"]) is not int or metadata["static_cpu"] != expected:
                raise ValueError(f"bank CPU specialization mismatch: {source.name}")
        abi_keys.add(metadata["abi_sha256"])
        validator(obj)
        result.append(obj)
    if len(abi_keys) != 1: raise ValueError("mixed runtime/header ABI keys in bank objects")
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--core-objects", type=Path, required=True)
    ap.add_argument("--bank-objects", type=Path, required=True)
    ap.add_argument("--banks", type=Path, required=True)
    ap.add_argument("--devkitpro", type=Path, default=Path("C:/devkitPro" if os.name == "nt" else "/opt/devkitpro"))
    ap.add_argument("--output", type=Path, default=REPO / "private/switch-variants")
    ap.add_argument("--name", default="vore-bench-llvm")
    ap.add_argument("--lto", action="store_true")
    args = ap.parse_args()
    if not re.fullmatch(r"[a-z0-9-]{1,64}", args.name): ap.error("name must be a simple lowercase basename")
    spec = importlib.util.spec_from_file_location("llvm_bank_build", HERE / "build_switch_llvm_banks.py")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    core = sorted(p.resolve() for p in args.core_objects.glob("*.o") if not p.name.startswith("bank_"))
    if not core or not any(p.name == "title_bank_registry.o" for p in core):
        ap.error("missing private runtime objects/registry")
    for p in core: helper.validate_object(p)
    banks = bank_objects(args.banks.resolve(), args.bank_objects.resolve(), helper.validate_object)
    dkp, out = args.devkitpro.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["DEVKITPRO"] = dkp.as_posix()
    suffix = ".exe" if os.name == "nt" else ""
    elf, nro, nacp = (out / (args.name + "." + ext) for ext in ("elf", "nro", "nacp"))
    link = ["-march=armv8-a+crc+crypto", "-mtune=cortex-a57", "-mtp=soft", "-fPIE",
            *(p.as_posix() for p in core + banks),
            f"-specs={(dkp / 'libnx/switch.specs').as_posix()}",
            f"-L{(dkp / 'libnx/lib').as_posix()}", "-lnx", "-o", elf.as_posix()]
    if args.lto: link[:0] = ["-flto=3", "-O3"]
    response = out / (args.name + ".rsp")
    response.write_text("\n".join('"' + p.replace('"', '\\"') + '"' for p in link))
    subprocess.run([str(dkp / ("devkitA64/bin/aarch64-none-elf-g++" + suffix)), "@" + response.as_posix()], env=env, check=True)
    subprocess.run([str(dkp / ("tools/bin/nacptool" + suffix)), "--create", args.name,
                    "vore-nx-dev", "0.2.0", str(nacp)], env=env, check=True)
    subprocess.run([str(dkp / ("tools/bin/elf2nro" + suffix)), str(elf), str(nro),
                    "--nacp=" + str(nacp)], env=env, check=True)
    print(f"Linked {len(core)} runtime + {len(banks)} bank objects: {nro}")
    print("ROM-derived experimental NRO. DO NOT DISTRIBUTE. Benchmark/parity not established by linking.")


if __name__ == "__main__":
    main()
