import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("verify_install", Path(__file__).resolve().parents[1] / "tools/verify_install.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ManifestTests(unittest.TestCase):
    def parse(self, rows):
        with tempfile.TemporaryDirectory(prefix="vore-verify-test-") as directory:
            path = Path(directory) / "manifest.tsv"
            path.write_text("vore-nx-install\t1\nrom-sha256\t" + module.SUPPORTED +
                            "\ngame-code\tCLJP\nrevision\t0\nname\toffset\tsize\tload\tentry\tsha256\n" + rows,
                            encoding="ascii")
            return module.parse_manifest(path)

    def test_numeric_filename(self):
        records = self.parse("file_000001.bin\t10\t20\t0\t0\t" + "a" * 64 + "\n")
        self.assertEqual(records["file_000001.bin"][0], (10, 20, 0, 0))

    def test_no_traversal(self):
        with self.assertRaises(ValueError):
            self.parse("../private.bin\t10\t20\t0\t0\t" + "a" * 64 + "\n")

    def test_no_duplicate_rows(self):
        row = "arm9.bin\t10\t20\t0\t0\t" + "a" * 64 + "\n"
        with self.assertRaises(ValueError):
            self.parse(row + row)

    def test_no_negative_range(self):
        with self.assertRaises(ValueError):
            self.parse("arm9.bin\t-1\t20\t0\t0\t" + "a" * 64 + "\n")


if __name__ == "__main__":
    unittest.main()
