import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("save_import", Path(__file__).resolve().parents[1] / "tools/import_save.py")
save = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(save)


class SaveImportTests(unittest.TestCase):
    raw = bytes(range(256)) * 32

    def test_raw_and_known_padding(self):
        self.assertEqual(save.normalize_save(self.raw), self.raw)
        for padding in (b"\xff", b"\x00"):
            self.assertEqual(save.normalize_save(self.raw + padding * (512*1024-8192)), self.raw)
        self.assertEqual(save.normalize_save(self.raw * 64), self.raw)

    def test_rejects_ambiguous_containers_and_sizes(self):
        for data in (b"", self.raw[:-1], self.raw + b"metadata", self.raw * 65,
                     self.raw + b"\xaa\xbb" * 4096):
            with self.assertRaises(ValueError): save.normalize_save(data)

    def test_nonoverwrite_and_original_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            src, out = Path(d)/"original.sav", Path(d)/"rom.sav"
            src.write_bytes(self.raw * 2)
            self.assertEqual(save.import_save(src, out), 8192)
            self.assertEqual(src.read_bytes(), self.raw * 2)
            self.assertEqual(out.read_bytes(), self.raw)
            with self.assertRaises(FileExistsError): save.import_save(src, out)
            with self.assertRaises(ValueError): save.import_save(src, src)
