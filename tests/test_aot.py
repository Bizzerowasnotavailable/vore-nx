"""Synthetic-only tests: never open the user's cartridge."""
import hashlib
import importlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import tomllib
import unittest
from unittest import mock

sys.dont_write_bytecode = True
TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import aot


def fixture():
    data = bytearray(16384)
    data[12:16] = b"CLJP"
    struct.pack_into("<4I", data, 0x20, 0x200, 0x02000000, 0x02000000, 0x100)
    struct.pack_into("<4I", data, 0x30, 0x400, 0x02380000, 0x02380000, 0x100)
    # Two tiny synthetic main images, one FAT entry and one overlay descriptor.
    data[0x200:0x204] = data[0x400:0x404] = bytes.fromhex("1eff2fe1")
    struct.pack_into("<2I", data, 0x48, 0x700, 8)
    struct.pack_into("<2I", data, 0x700, 0x800, 0x900)
    struct.pack_into("<2I", data, 0x50, 0x900, 32)
    struct.pack_into("<8I", data, 0x900, 42, 0x02010000, 0x100, 0x20,
                     0x02010020, 0x02010024, 0, 0x01000100)
    struct.pack_into("<H", data, 0x15e, aot.crc16(data[:0x15e]))
    return bytes(data)


class AotTests(unittest.TestCase):
    def setUp(self):
        parent = aot.WORK / "tmp"
        parent.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="aot-synthetic-tests-", dir=parent)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_reject_public_output_paths(self):
        for path in (aot.REPO / "generated", aot.REPO / "tools/out", aot.WORKSPACE / "out",
                     aot.REPO / "private/../../public", aot.REPO / "private", aot.WORK):
            with self.subTest(path=path), self.assertRaises(ValueError):
                aot.private_path(path)

    def test_accept_only_private_roots(self):
        for path in (aot.REPO / "private/aot/example", self.root / "output"):
            self.assertEqual(aot.private_path(path), path.resolve())

    def test_prepare_rejects_public_path_after_valid_synthetic_hash(self):
        data = fixture()
        rom = self.root / "synthetic.nds"
        rom.write_bytes(data)
        output = aot.REPO / "tools" / "must-not-create-aot-output"
        with mock.patch.object(aot, "SUPPORTED_SHA256", hashlib.sha256(data).hexdigest()):
            with self.assertRaisesRegex(ValueError, "Output must be below"):
                aot.prepare(rom, output)
        self.assertFalse(output.exists())

    def test_reject_symlink_escape(self):
        public = self.root / "public"
        public.mkdir()
        link = self.root / "private/link"
        link.parent.mkdir()
        try:
            link.symlink_to(public, target_is_directory=True)
        except OSError:
            self.skipTest("Host does not permit symlink creation")
        with self.assertRaises(ValueError):
            aot.private_path(link / "out", repo=self.root, workspace=self.root / "workspace")

    def test_unsupported_hash_writes_nothing(self):
        rom = self.root / "synthetic.nds"
        rom.write_bytes(fixture())
        output = self.root / "must-not-exist"
        with mock.patch.object(aot, "cartridge_metadata") as parse:
            with self.assertRaisesRegex(ValueError, "Unsupported ROM SHA256"):
                aot.prepare(rom, output)
            parse.assert_not_called()
        self.assertFalse(output.exists())

    def test_crc_and_revision_checked_after_hash(self):
        for offset, value in ((0, 1), (0x1e, 1), (0x12, 2), (12, ord("X"))):
            data = bytearray(fixture())
            data[offset] = value
            rom = self.root / "invalid.nds"
            rom.write_bytes(data)
            with mock.patch.object(aot, "SUPPORTED_SHA256", hashlib.sha256(data).hexdigest()):
                with self.assertRaises(ValueError):
                    aot.verify_rom(rom)

    def test_prepare_actual_size_hash_and_overlay_metadata_only(self):
        data = fixture()
        rom = self.root / "synthetic.nds"
        rom.write_bytes(data)
        output = self.root / "prepared"
        with mock.patch.object(aot, "SUPPORTED_SHA256", hashlib.sha256(data).hexdigest()), \
                mock.patch("urllib.request.urlopen", side_effect=AssertionError("implicit network")):
            manifest = aot.prepare(rom, output)
            self.assertEqual(manifest, aot.prepare(rom, output))  # deterministic/idempotent
        for cpu in (9, 7):
            binary = (output / f"inputs/arm{cpu}.bin").read_bytes()
            config = tomllib.loads((output / f"inputs/arm{cpu}.toml").read_text())
            self.assertEqual(config["program"]["size"], len(binary))
            self.assertEqual(config["identity"]["sha1"], hashlib.sha1(binary).hexdigest())
            self.assertNotIn("entry_point", config)
        overlays = json.loads((output / "overlays.json").read_text())["overlays"]
        self.assertEqual(len(overlays), 1)
        self.assertEqual(overlays[0]["id"], 42)
        self.assertTrue(overlays[0]["compressed_in_rom"])
        self.assertFalse((output / "overlays").exists())

    def test_changed_prepared_input_is_not_overwritten(self):
        data = fixture()
        rom = self.root / "synthetic.nds"
        rom.write_bytes(data)
        output = self.root / "prepared"
        with mock.patch.object(aot, "SUPPORTED_SHA256", hashlib.sha256(data).hexdigest()):
            aot.prepare(rom, output)
            target = output / "inputs/arm9.bin"
            target.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "Existing output differs"):
                aot.prepare(rom, output)
            self.assertEqual(target.read_bytes(), b"changed")

    def test_invalid_cartridge_ranges(self):
        for offset, value in ((0x20, 0xfffffff0), (0x28, 0xfffffff0), (0x4c, 9), (0x704, 0x7ff)):
            data = bytearray(fixture())
            struct.pack_into("<I", data, offset, value)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                aot.cartridge_metadata(data)

    def test_footer_and_decompression_length_guard(self):
        raw = b"A" * 64 + struct.pack("<2I", (8 << 24) | 24, 16)
        footer = aot.compression_footer(raw)
        self.assertEqual(footer["passthrough_bytes"], 48)
        self.assertEqual(footer["expected_size"], 88)
        meta = dict(cpu=9, load=0x02000000, entry=0x02000000, raw_size=len(raw), rom_offset=512)
        expanded = raw[:48] + b"B" * 40
        with mock.patch.object(aot, "load_decompressor", return_value=lambda _: expanded):
            image, record, _, _ = aot.prepare_main(raw, meta, "unused")
        self.assertEqual(image, expanded)
        self.assertEqual(record["prepared_size"], len(expanded))
        with mock.patch.object(aot, "load_decompressor", return_value=lambda _: b"bad"):
            with self.assertRaisesRegex(ValueError, "disagrees"):
                aot.prepare_main(raw, meta, "unused")

    def test_sdk_footer_size_and_autoload_correspondence(self):
        load = 0x02000000
        raw = bytearray(256)
        struct.pack_into("<7I", raw, 32, load + 372, load + 384, load + 356,
                         load + 384, load + 512, load + len(raw), 0x04000000)
        raw[60:68] = aot.SDK_MAGIC
        struct.pack_into("<2I", raw, 248, (8 << 24) | 64, 128)
        expanded = bytearray(raw[:192]) + bytearray(192)
        struct.pack_into("<3I", expanded, 372, 0x01ff8000, 16, 4)
        meta = dict(cpu=9, load=load, entry=load, raw_size=len(raw), rom_offset=512)
        with mock.patch.object(aot, "load_decompressor", return_value=lambda _: expanded):
            image, record, _, _ = aot.prepare_main(raw, meta, "unused")
        self.assertEqual(len(image), 384)
        self.assertEqual(record["code_copies"][0]["source_start"], load + 356)
        self.assertEqual(record["compression"]["sdk"]["compressed_static_end"], load + len(raw))
        self.assertEqual(image[32:68], raw[32:68])  # no SDK-field patching

    @unittest.skipUnless(aot.DEFAULT_NDSPY.is_file(), "optional pinned wheel not bootstrapped")
    def test_pinned_decompressor_synthetic_round_trip(self):
        decompress = aot.load_decompressor(aot.DEFAULT_NDSPY)
        compression = importlib.import_module("ndspy.codeCompression")
        image = b"Synthetic code-compression fixture!" * 200 + bytes(range(256))
        raw = compression.compress(image)
        self.assertLess(len(raw), len(image))
        self.assertEqual(decompress(raw), image)
        meta = dict(cpu=7, load=0x02000000, entry=0x02000000, raw_size=len(raw), rom_offset=512)
        prepared, record, _, _ = aot.prepare_main(raw, meta, aot.DEFAULT_NDSPY)
        self.assertEqual(prepared, image)
        self.assertEqual(record["prepared_size"], len(image))

    def test_raw_startup_excludes_compressed_payload(self):
        raw = b"A" * 64 + struct.pack("<2I", (8 << 24) | 24, 16)
        meta = dict(cpu=9, load=0x02000000, entry=0x02000000, raw_size=len(raw), rom_offset=512)
        with mock.patch.object(aot, "load_decompressor", side_effect=AssertionError("dependency not needed")):
            image, record, excluded, bounded = aot.prepare_main(raw, meta, "absent", True)
        self.assertEqual(image, raw)
        self.assertEqual(record["compression"]["mode"], "raw-startup-only")
        config = tomllib.loads(aot.config_text(record, excluded, bounded))
        self.assertEqual(config["data_range"][0]["start"], meta["load"] + 48)
        self.assertEqual(config["data_range"][0]["end"], meta["load"] + len(raw))

    def test_missing_and_tampered_dependency_refused(self):
        with self.assertRaisesRegex(ValueError, "Pinned ndspy is absent"):
            aot.load_decompressor(self.root / "absent.whl")
        bad = self.root / "bad.whl"
        bad.write_bytes(b"not the pinned dependency")
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            aot.load_decompressor(bad)

    def test_sdk_copy_descriptors_are_not_entry_seeds(self):
        image = bytearray(128)
        load = 0x02000000
        struct.pack_into("<3I", image, 116, 0x01ff8000, 16, 4)
        settings = dict(autoload_start=load + 116, autoload_end=load + 128, autoload_data=load + 100)
        copies = aot.autoload_copies(image, load, settings)
        self.assertEqual(copies[0]["size"], 16)
        meta = dict(cpu=9, load=load, entry=load, prepared_size=128,
                    prepared_sha1=hashlib.sha1(image).hexdigest(), code_copies=copies)
        config = tomllib.loads(aot.config_text(meta))
        self.assertIn("code_copy", config)
        self.assertNotIn("entry_point", config)

    def test_uncertain_sdk_compression_refuses_or_bounds_raw_entry(self):
        raw = bytearray(128)
        load = 0x02000000
        struct.pack_into("<7I", raw, 32, load + 116, load + 128, load + 100,
                         load + 128, load + 256, load + 120, 0x04000000)
        raw[60:68] = aot.SDK_MAGIC
        meta = dict(cpu=9, load=load, entry=load, raw_size=len(raw), rom_offset=512)
        with self.assertRaisesRegex(ValueError, "compressed end does not match"):
            aot.prepare_main(raw, meta, "absent")
        _, record, excluded, bounded = aot.prepare_main(raw, meta, "absent", True)
        self.assertTrue(bounded)
        config = tomllib.loads(aot.config_text(record, excluded, bounded))
        self.assertTrue(config["program"]["authoritative_entry_points"])
        self.assertEqual(config["entry_point"][0]["size"], 4)

    def test_thumb_entry_has_explicit_mode(self):
        meta = dict(cpu=7, load=0x02380000, entry=0x02380001, prepared_size=16,
                    prepared_sha1="0" * 40, code_copies=[])
        config = tomllib.loads(aot.config_text(meta))
        self.assertEqual(config["program"]["entry_pc"], 0x02380000)
        self.assertEqual(config["entry_point"][0]["mode"], "thumb")

    def test_generated_outputs_checked_not_just_exit_status(self):
        bank = "bis_arm9_main"
        with self.assertRaisesRegex(ValueError, "Missing generated"):
            aot.verify_generated(self.root, bank)
        (self.root / f"{bank}.h").write_text("void " + bank + "_entry(void);")
        (self.root / f"{bank}_00.c").write_text("void " + bank + "_entry(void) {}")
        dispatch = self.root / f"{bank}_dispatch.c"
        dispatch.write_text(f"const NdsDispatchEntry g_dispatch_{bank}[] = {{}};\n"
                            f"const unsigned g_dispatch_{bank}_len = 0;")
        with self.assertRaisesRegex(ValueError, "empty, incomplete"):
            aot.verify_generated(self.root, bank)
        dispatch.write_text(f"static const NdsStaticValidation g_validation_0 = {{0}};\n"
                            f"const NdsDispatchEntry g_dispatch_{bank}[] = {{\n"
                            f"    {{0x02000000u, 0u, {bank}_entry, &g_validation_0}},\n}};\n"
                            f"const unsigned g_dispatch_{bank}_len = 1;")
        self.assertEqual(len(aot.verify_generated(self.root, bank)), 3)
        dispatch.write_text(dispatch.read_text().replace("_len = 1", "_len = 2"))
        with self.assertRaisesRegex(ValueError, "row count"):
            aot.verify_generated(self.root, bank)

    def test_mismatched_runtime_headers_refused_before_compiling(self):
        source = self.root / "source"
        for name in aot.RUNTIME_HEADER_PINS:
            header = source / name
            header.parent.mkdir(parents=True, exist_ok=True)
            header.write_text("synthetic wrong ABI header")
        with mock.patch.object(aot, "run", side_effect=AssertionError("must not invoke compiler")):
            with self.assertRaisesRegex(ValueError, "Runtime ABI header differs"):
                aot.smoke_objects(self.root, "unused", source)


if __name__ == "__main__":
    unittest.main()
