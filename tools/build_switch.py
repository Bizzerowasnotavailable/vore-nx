#!/usr/bin/env python3
"""Build through devkitPro MSYS on Windows, or make on Unix hosts."""
import argparse
import os
from pathlib import Path, PureWindowsPath
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def msys_path(path):
    path = PureWindowsPath(path)
    if not path.drive or path.drive.startswith("\\"):
        raise ValueError("Windows builds require a local drive path, not a network share")
    return "/" + path.drive[0].lower() + "/" + "/".join(path.parts[1:])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--devkitpro", type=Path)
    args = parser.parse_args()
    if args.jobs < 1 or args.jobs > 64:
        parser.error("jobs must be 1..64")
    if os.name == "nt":
        devkit = args.devkitpro
        if devkit is None:
            candidates = [Path(os.environ.get("DEVKITPRO", "")), Path("C:/devkitPro")]
            devkit = next((p for p in candidates if (p / "msys2/usr/bin/bash.exe").is_file()), candidates[-1])
        bash = devkit / "msys2/usr/bin/bash.exe"
        if not bash.is_file():
            parser.error("devkitPro MSYS bash not found; supply --devkitpro")
        command = [str(bash), "-lc", 'cd "$1" && make -j"$3" PYTHON="$2"',
                   "vore-build", msys_path(ROOT), msys_path(sys.executable), str(args.jobs)]
    else:
        command = ["make", "-C", str(ROOT), f"-j{args.jobs}", f"PYTHON={sys.executable}"]
    subprocess.run(command, cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(ROOT / "tools/package_release.py"), "--check"], check=True)


if __name__ == "__main__":
    main()
