#!/usr/bin/env python3
"""Allowlist-only public source/NRO package. Never traverses private or .git."""
import argparse
import hashlib
from pathlib import Path
import struct
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = (
    ".gitignore", "README.md", "JOURNEY.MD", "LICENSE", "Makefile",
    "CMakeLists.txt",
)
SOURCE_DIRS = ("include", "source", "tests", "tools", "docs", ".github/workflows")
EXTENSIONS = {".hpp", ".cpp", ".py", ".md", ".yml"}


def audit_nro(data):
    if len(data) < 0x80 or data[0x10:0x14] != b"NRO0":
        raise ValueError("not an NRO0 executable")
    size = struct.unpack_from("<I", data, 0x18)[0]
    if size < 0x80 or size + 56 > len(data) or data[size:size + 4] != b"ASET":
        raise ValueError("missing/truncated NRO asset metadata")
    magic, version, icon_off, icon_size, nacp_off, nacp_size, romfs_off, romfs_size = \
        struct.unpack_from("<4sI6Q", data, size)
    if version != 0 or icon_size or romfs_size:
        raise ValueError("release must have no icon or ROMFS; metadata version must be 0")
    if nacp_size != 0x4000 or nacp_off < 56 or size + nacp_off + nacp_size != len(data):
        raise ValueError("unexpected NACP layout or trailing embedded payload")
    for marker in (b"C:/Users/", b"C:\\Users\\", b"/home/", b"-----BEGIN PRIVATE KEY-----",
                   b"-----BEGIN RSA PRIVATE KEY-----", b"g_dispatch_bis_", b"g_dispatch_arm9_bios"):
        if marker in data:
            raise ValueError("sensitive path/key or ROM-derived dispatch marker in NRO")
    return hashlib.sha256(data).hexdigest()


def source_paths():
    paths = [ROOT / name for name in SOURCE_FILES]
    for directory in SOURCE_DIRS:
        base = ROOT / directory
        if base.exists():
            paths.extend(p for p in base.rglob("*") if p.is_file() and p.suffix in EXTENSIONS)
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise ValueError(f"symlink/escaped source path: {path.name}")
        if not path.is_file():
            raise ValueError(f"missing public source: {path.name}")
        data = path.read_bytes()
        if b"\x00" in data:
            raise ValueError(f"binary content in source allowlist: {path.name}")
    return sorted(paths)


def package(destination, nro):
    data = nro.read_bytes()
    digest = audit_nro(data)
    paths = source_paths()
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation: never overwrite an existing release archive.
    with zipfile.ZipFile(destination, "x", zipfile.ZIP_DEFLATED) as archive:
        def write(name, content):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED)
        for path in paths:
            write("source/" + path.relative_to(ROOT).as_posix(), path.read_bytes())
        write("switch/vore-nx/vore-nx.nro", data)
        write("SHA256SUMS", f"{digest}  switch/vore-nx/vore-nx.nro\n")
    print(f"Packaged {len(paths)} source files + asset-free NRO: {destination.name}")
    print(f"NRO SHA-256: {digest}")
    print("Structural checks are a safety net, not a legal opinion or proof of game compatibility.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nro", type=Path, default=ROOT / "vore-nx.nro")
    parser.add_argument("--output", type=Path, default=ROOT / "dist/vore-nx-0.1.1.zip")
    parser.add_argument("--check", action="store_true", help="audit only, do not package")
    args = parser.parse_args()
    if args.check:
        print("NRO SHA-256:", audit_nro(args.nro.read_bytes()))
        print("Public source files:", len(source_paths()))
    else:
        package(args.output, args.nro)


if __name__ == "__main__":
    main()
