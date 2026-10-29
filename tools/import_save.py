#!/usr/bin/env python3
"""Convert a matching CLJP raw/known-padded battery SAV without modifying it."""
import argparse
from pathlib import Path

SAVE_BYTES = 8192
MAX_BYTES = 512 * 1024


def normalize_save(data):
    if len(data) == SAVE_BYTES:
        return data
    if not SAVE_BYTES < len(data) <= MAX_BYTES or len(data) % SAVE_BYTES:
        raise ValueError("expected an 8192-byte raw SAV or known padding up to 512 KiB; export raw SAV from container formats first")
    raw, tail = data[:SAVE_BYTES], data[SAVE_BYTES:]
    if all(b == 0xFF for b in tail) or all(b == 0 for b in tail) or data == raw * (len(data) // SAVE_BYTES):
        return raw
    raise ValueError("extra data is not uniform padding or identical mirrored copies; refusing to truncate")


def import_save(source, output):
    if source.resolve() == output.resolve():
        raise ValueError("input and output must be different files")
    # Bound the read before allocating, and never write until all checks pass.
    with source.open("rb") as f:
        raw = normalize_save(f.read(MAX_BYTES + 1))
    with output.open("xb") as f:
        f.write(raw)
    return len(raw)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", type=Path)
    ap.add_argument("output", type=Path, help="new .sav file; never overwritten")
    args = ap.parse_args()
    try:
        size = import_save(args.source, args.output)
    except (OSError, ValueError) as exc:
        ap.error(str(exc))
    print(f"Created {size}-byte raw save; original unchanged. Game/region validity is not inferred.")


if __name__ == "__main__":
    main()
