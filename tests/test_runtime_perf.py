import importlib.util
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


patcher = module("perf_patch", "tools/private/patch_runtime_perf.py")
bench = module("bench_compare", "tools/private/compare_switch_bench.py")
llvm = module("llvm_build", "tools/private/build_switch_llvm_banks.py")
link = module("variant_link", "tools/private/link_switch_variant.py")


class RuntimePerfTests(unittest.TestCase):
    def test_static_cpu_inference_is_exact(self):
        self.assertEqual(llvm.static_cpu(Path("bis_arm9_main_00.c")), 0)
        self.assertEqual(llvm.static_cpu(Path("bis_arm7_alias_037f7de4.c")), 1)
        self.assertEqual(llvm.static_cpu(Path("freebios_arm9_dispatch.c")), 0)
        with self.assertRaises(ValueError): llvm.static_cpu(Path("unknown.c"))
        with self.assertRaises(ValueError): llvm.static_cpu(Path("bis_arm9_arm7.c"))
    def test_native_clock_and_frequency_calibration(self):
        header = "#include <string>\ninline uint64_t tick_now() {\n#if defined(NDS_DISPATCH_TIMING_TSC)\n"
        source = "double measure_ns_per_tick() {\n#if defined(NDS_DISPATCH_TIMING_TSC)\n"
        h, c = patcher.clock_header(header), patcher.clock_source(source)
        self.assertIn("return armGetSystemTick();", h)
        self.assertIn("defined(NDS_SWITCH) && defined(__aarch64__)", h)
        self.assertIn("1000000000.0 / static_cast<double>(armGetSystemTickFreq())", c)
        self.assertEqual(patcher.clock_header(h), h)
        self.assertEqual(patcher.clock_source(c), c)
        with self.assertRaises(ValueError): patcher.clock_header("unexpected header")
        with self.assertRaises(ValueError): patcher.clock_source("unexpected source")

    def test_minimal_profile_patch_matches_constructor_not_destructor(self):
        text = ("inline uint8_t nds_emu_enter(NdsEmuBucket bucket) {\n"
                "inline void nds_emu_exit(uint8_t prev) {\n"
                "    NdsEmuRound() {\n    ~NdsEmuRound() {\n"
                "explicit NdsEmuBusRegion(uint32_t addr) {\n")
        result = patcher.minimal_profiling_header(text, "emu_profile.h")
        self.assertIn("sampling_ = false; return;", result)
        self.assertIn("~NdsEmuRound() {\n", result)
        self.assertEqual(patcher.minimal_profiling_header(result, "emu_profile.h"), result)

    @staticmethod
    def log(fps=10, digest="0123456789ABCDEF", target=672228000):
        return (f"performance: {fps}.00 guest frames/s scheduler=95.00ms present=5.00ms\n"
                f"checkpoint frame=600 target={target} pixels64={digest}/0123456789ABCDEF\n"
                "benchmark: complete\n")

    def test_benchmark_compares_targets_pixels_and_timing(self):
        result = bench.compare(self.log(), self.log(20))
        self.assertEqual(result["mismatches"], [])
        self.assertEqual(result["median_fps_ratio"], 2)
        result = bench.compare(self.log(), self.log(digest="FEDCBA9876543210"))
        self.assertEqual(result["mismatches"], [600])
        result = bench.compare(self.log(), self.log(target=1))
        self.assertEqual(result["mismatches"], [600])

    def test_incomplete_fatal_and_missing_checkpoints_refused(self):
        with self.assertRaises(ValueError): bench.parse("not completed")
        with self.assertRaises(ValueError): bench.parse(self.log() + "fatal: error")
        with self.assertRaises(ValueError): bench.parse("benchmark: complete")
        with self.assertRaises(ValueError): bench.compare(self.log(), self.log().replace("frame=600", "frame=720"))

    def test_bank_architecture_source_and_abi_checks(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            banks, objects = root / "banks", root / "objects"
            banks.mkdir(); objects.mkdir()
            header = bytearray(64)
            header[:6] = b"\x7fELF\x02\x01"
            struct.pack_into("<HH", header, 16, 1, 183)
            source = banks / "fixture.c"
            source.write_text("// synthetic source")
            obj = objects / "bank_fixture.o"
            obj.write_bytes(header)
            llvm.validate_object(obj)
            meta = obj.with_suffix(".json")
            meta.write_text(json.dumps({"source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                                        "abi_sha256": "fixture ABI"}))
            self.assertEqual(link.bank_objects(banks, objects, llvm.validate_object), [obj])
            source.write_text("// changed source")
            with self.assertRaises(ValueError): link.bank_objects(banks, objects, llvm.validate_object)
            header[18] = 62 # x86-64 is not a Switch object
            obj.write_bytes(header)
            with self.assertRaises(ValueError): llvm.validate_object(obj)
