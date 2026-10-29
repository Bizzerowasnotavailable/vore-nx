"""ROM/compiler-free checks of the local runtime build driver."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "runtime_build", ROOT / "tools/private/build_switch_runtime.py")
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)


class RuntimeBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "workspace with spaces"
        self.nds = self.root / "nds"
        self.bios = self.root / "bios"
        self.out = self.root / "out"
        self.frontend = self.root / "frontend"
        self.dkp = self.root / "dkp"
        self.calls = []
        paths = [self.nds / "runner/src" / f"{n}.cpp" for n in build.CORE_UNITS]
        paths += [self.nds / "external/arm-recomp-core/common" / f"{n}.cpp"
                  for n in ("arm_decode", "thumb_decode", "arm_ir", "interpreter")]
        paths += [self.nds / "external/arm-recomp-core/profiles/armv5te_nds/arm_codegen.cpp"]
        paths += [self.nds / "runner/src/net" / f"{n}.cpp"
                  for n in ("net_ring", "net_classify")]
        paths += [self.nds / "runner/vendor/melonds" / f"{n}.cpp"
                  for n in ("GPU3D", "GPU3D_Soft", "Savestate")]
        paths += [self.nds / "vendor/freebios/freebios_images.cpp",
                  self.nds / "recompiler/support/sha1.cpp"]
        paths += [self.frontend / f"{n}.cpp" for n in
                  ("switch_main", "switch_wifi_stub", "switch_host_info", "nds_host_shims")]
        paths += [self.bios / f"freebios_{cpu}{tail}.c"
                  for cpu in ("arm9", "arm7") for tail in ("", "_dispatch")]
        self.header = self.nds / "runner/src/state.h"
        paths.append(self.header)
        suffix = ".exe" if os.name == "nt" else ""
        paths += [self.dkp / "devkitA64/bin" / ("aarch64-none-elf-" + n + suffix)
                  for n in ("gcc", "g++")]
        for p in paths:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("// synthetic build fixture\n")
        (self.nds / "runner/src/io.cpp").write_text(
            '#include "io.h"\ncase 0x50: g_tsc_conv = g_tsc_x; break;\n')
        (self.nds / "runner/src/dispatch_timing.h").write_text(
            '#include <string>\ninline uint64_t tick_now() {\n#if defined(NDS_DISPATCH_TIMING_TSC)\n')
        (self.nds / "runner/src/dispatch_timing.cpp").write_text(
            'double measure_ns_per_tick() {\n#if defined(NDS_DISPATCH_TIMING_TSC)\n')

    def run_build(self, fail=False, banks=None, extra=()):
        def run(command, **kwargs):
            self.calls.append(command)
            if "--out" in command:
                Path(command[command.index("--out") + 1]).write_text("// registry fixture\n")
            if "-c" in command:
                target = Path(command[command.index("-o") + 1])
                target.write_bytes(b"synthetic object")
                if fail:
                    raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 0)

        argv = ["build", "--nds", str(self.nds), "--bios-banks", str(self.bios),
                "--output", str(self.out), "--devkitpro", str(self.dkp), "--jobs", "1"]
        if banks:
            argv += ["--banks", str(banks)]
        argv += list(extra)
        with patch.object(sys, "argv", argv), patch.object(build, "FRONTEND", self.frontend), \
                patch.object(build, "REPO", self.root), \
                patch.object(build.subprocess, "run", side_effect=run), \
                contextlib.redirect_stdout(io.StringIO()):
            build.main()

    def test_cache_and_header_invalidation(self):
        self.run_build()
        count = sum("-c" in c for c in self.calls)
        self.assertGreater(count, 40)
        self.calls.clear()
        self.run_build()
        self.assertFalse(any("-c" in c for c in self.calls))
        self.header.write_text("// changed ABI\n")
        self.calls.clear()
        self.run_build()
        self.assertEqual(sum("-c" in c for c in self.calls), count)

    def test_failure_preserves_old_object_and_does_not_link(self):
        obj = self.out / "obj-interpreter/core_runtime_arm.o"
        obj.parent.mkdir(parents=True)
        obj.write_bytes(b"old good object")
        with self.assertRaises(subprocess.CalledProcessError):
            self.run_build(fail=True)
        self.assertEqual(obj.read_bytes(), b"old good object")
        self.assertFalse(obj.with_suffix(".sha256").exists())
        self.assertFalse(any(any(a.startswith("@") for a in c) for c in self.calls))

    def test_stale_objects_not_linked(self):
        obj = self.out / "obj-interpreter/unrelated_bank.o"
        obj.parent.mkdir(parents=True)
        obj.write_bytes(b"stale")
        self.run_build()
        response = (obj.parent / "link.rsp").read_text()
        self.assertNotIn("unrelated_bank", response)
        self.assertIn("switch_main.o", response)

    def test_private_bank_registry_and_giant_optimization(self):
        banks = self.root / "banks"
        banks.mkdir(parents=True)
        (banks / "bis_arm9_main_dispatch.c").write_text("// synthetic dispatch\n")
        (banks / "bis_arm9_main.c").write_bytes(b"/" * build.BIG_BYTES)
        self.run_build(banks=banks)
        compiles = [c for c in self.calls if "-c" in c]
        self.assertIn("bis_arm9_main.c", compiles[0][compiles[0].index("-c") + 1])
        self.assertIn("-O1", compiles[0])
        self.assertTrue(all("-O2" in c for c in compiles[1:]))
        self.assertTrue(all("-DVORE_PRIVATE_BANKS=1" in c for c in compiles))
        response = (self.out / "obj-private/link.rsp").read_text()
        self.assertIn("title_bank_registry.o", response)
        self.assertIn("bank_bis_arm9_main.o", response)

    def test_runtime_only_lto_never_links_or_builds_game_banks(self):
        banks = self.root / "banks"
        banks.mkdir(parents=True)
        (banks / "bis_arm9_main_dispatch.c").write_text("// synthetic dispatch\n")
        self.run_build(banks=banks, extra=("--runtime-only", "--optimization", "O3", "--lto"))
        compiles = [c for c in self.calls if "-c" in c]
        self.assertTrue(all("-O3" in c and "-flto=1" in c for c in compiles))
        self.assertFalse(any("bank_bis_arm9" in " ".join(c) for c in compiles))
        self.assertFalse(any(any(a.startswith("@") for a in c) for c in self.calls))

    def test_whole_bank_lto_uses_ir_objects_and_strict_link_type_check(self):
        banks = self.root / "banks"
        banks.mkdir(parents=True)
        (banks / "bis_arm9_main_dispatch.c").write_text("// synthetic dispatch\n")
        self.run_build(banks=banks, extra=("--optimization", "O3", "--lto", "--bank-lto"))
        compiles = [c for c in self.calls if "-c" in c]
        self.assertTrue(all("-flto=1" in c and "-fno-fat-lto-objects" in c for c in compiles))
        bank = next(c for c in compiles if "bank_bis_arm9_main_dispatch.o.tmp" in " ".join(c))
        self.assertIn("-DNDS_STATIC_CPU=0", bank)
        response = (self.out / "obj-private/link.rsp").read_text()
        self.assertIn("-Werror=lto-type-mismatch", response)


if __name__ == "__main__":
    unittest.main()
