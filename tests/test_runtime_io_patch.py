import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("io_patch", Path(__file__).resolve().parents[1] / "tools/private/patch_runtime_io.py")
patcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(patcher)


class MicPatchTests(unittest.TestCase):
    def test_explicit_channel_and_idempotence(self):
        original = '#include "io.h"\ncase 0x50: g_tsc_conv = g_tsc_x; break;\n'
        result = patcher.microphone_source(original)
        self.assertIn("case 0x60: g_tsc_conv = vore::microphone::sample();", result)
        self.assertIn('"runtime_microphone.hpp"', result)
        self.assertEqual(patcher.microphone_source(result), result)

    def test_unknown_dependency_refused(self):
        with self.assertRaises(ValueError): patcher.microphone_source("unexpected implementation")
