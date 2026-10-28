#!/usr/bin/env python3
"""Redact known upstream SDK diagnostic paths, keeping NRO offsets unchanged.

devkitA64's prebuilt newlib printf implementation contains two assert strings
with its package builder's absolute home directory. This does not strip code
or assets: only those diagnostic C strings are replaced by neutral basenames.
Unknown paths are NOT rewritten; the separate release audit rejects them.
"""
from pathlib import Path
import re
import sys

SDK_PATH = re.compile(rb"/home/[A-Za-z0-9_.-]+/projects/devkitpro/[^\x00\r\n]{1,512}\x00")


def sanitize(data):
    count = 0

    def replace(match):
        nonlocal count
        original = match.group()
        if b"/newlib/" not in original:
            return original
        replacement = b"<devkitPro>/" + original[:-1].rsplit(b"/", 1)[-1] + b"\x00"
        if len(replacement) > len(original):
            raise ValueError("SDK diagnostic replacement exceeds original string")
        count += 1
        return replacement.ljust(len(original), b"\x00")

    return SDK_PATH.sub(replace, data), count


if __name__ == "__main__":
    path = Path(sys.argv[1])
    data, count = sanitize(path.read_bytes())
    path.write_bytes(data)
    print(f"Redacted {count} upstream SDK diagnostic paths (no code changes).")
