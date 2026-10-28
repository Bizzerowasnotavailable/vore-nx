import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("package_release", Path(__file__).resolve().parents[1] / "tools/package_release.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def synthetic_nro():
    data = bytearray(0x80 + 56 + 0x4000)
    data[0x10:0x14] = b"NRO0"
    struct.pack_into("<I", data, 0x18, 0x80)
    struct.pack_into("<4sI6Q", data, 0x80, b"ASET", 0, 0, 0, 56, 0x4000, 0, 0)
    return data


class PackageTests(unittest.TestCase):
    def test_minimal_nro(self):
        self.assertEqual(len(module.audit_nro(synthetic_nro())), 64)

    def test_refuse_romfs(self):
        data = synthetic_nro()
        struct.pack_into("<Q", data, 0x80 + 48, 1)
        with self.assertRaises(ValueError):
            module.audit_nro(data)

    def test_refuse_trailing_payload(self):
        with self.assertRaises(ValueError):
            module.audit_nro(synthetic_nro() + b"not metadata")

    def test_refuse_personal_path(self):
        data = synthetic_nro()
        data[0x40:0x49] = b"C:/Users/"
        with self.assertRaises(ValueError):
            module.audit_nro(data)

    def test_refuse_bad_magic(self):
        with self.assertRaises(ValueError):
            module.audit_nro(bytes(512))

    def test_reproducible_archive(self):
        with tempfile.TemporaryDirectory(prefix="vore-package-test-") as directory:
            root = Path(directory)
            nro = root / "synthetic.nro"
            nro.write_bytes(synthetic_nro())
            with patch.object(module, "source_paths", return_value=[module.ROOT / "README.md"]):
                module.package(root / "first.zip", nro)
                module.package(root / "second.zip", nro)
            self.assertEqual((root / "first.zip").read_bytes(), (root / "second.zip").read_bytes())


if __name__ == "__main__":
    unittest.main()
