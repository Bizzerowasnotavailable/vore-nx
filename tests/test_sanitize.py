import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("sanitize_sdk_paths", Path(__file__).resolve().parents[1] / "tools/sanitize_sdk_paths.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SanitizeTests(unittest.TestCase):
    def test_redacts_only_known_sdk_path(self):
        original = b"prefix\x00/home/builder/projects/devkitpro/packages/newlib/src/dtoa.c\x00suffix"
        data, count = module.sanitize(original)
        self.assertEqual(count, 1)
        self.assertEqual(len(data), len(original))
        self.assertIn(b"<devkitPro>/dtoa.c\x00", data)
        self.assertTrue(data.endswith(b"suffix"))
        self.assertNotIn(b"/home/", data)

    def test_does_not_hide_unknown_paths(self):
        original = b"/home/synthetic-user/unexpected/file.cpp\x00"
        self.assertEqual(module.sanitize(original), (original, 0))

    def test_idempotent(self):
        data, _ = module.sanitize(b"/home/builder/projects/devkitpro/packages/newlib/src/dtoa.c\x00")
        self.assertEqual(module.sanitize(data), (data, 0))


if __name__ == "__main__":
    unittest.main()
