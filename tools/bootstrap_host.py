#!/usr/bin/env python3
"""Explicit, pinned development downloads. No pip/global installation."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request
import zipfile

REPO = Path(__file__).resolve().parents[1]
WORKSPACE = REPO.parent
WORK = WORKSPACE / "local-work"
NDS_COMMIT = "aa40b575b6f68a537f24ff3e4c94b567baa25587"
CORE_COMMIT = "705e71b8aff3ad64fe78f77c3c94bd93158554dd"
NDSPY_VERSION = "4.2.0"
NDSPY_SHA256 = "d3b03e57ef5ba450e766035e1908293f7a6ba1a738736fae42b2c66952abb85b"
PINS = {
    "ndspy": (
        "https://files.pythonhosted.org/packages/07/01/c60b57a0aa66074552acbbc16786b34c93caa72f3fdda64fada11866482a/ndspy-4.2.0-py3-none-any.whl",
        NDSPY_SHA256,
        "ndspy-4.2.0-py3-none-any.whl"),
    "zig": (
        "https://files.pythonhosted.org/packages/b9/6b/8ab0853a312108b4089747486366b824b5da89773cb56f661f9994de17db/ziglang-0.15.2-py3-none-win_amd64.whl",
        "ca80dc9c70dbdfdd9ee51d000de3501a95d33d9782ab9ab9b56f700484ebcd83",
        "ziglang-0.15.2-py3-none-win_amd64.whl"),
    "ndsrecomp": (
        f"https://codeload.github.com/RetroPortingToolKit/ndsrecomp/zip/{NDS_COMMIT}",
        "22f3965de48534ae7933970a7740a75f7c990d45a6d4c60b2aa4a05137f2d792",
        f"ndsrecomp-{NDS_COMMIT}.zip"),
    "core": (
        f"https://codeload.github.com/mstan/arm-recomp-core/zip/{CORE_COMMIT}",
        "7c015e15481a75903fe56f936421eca308f1cde80128a6e0b49539abef9568d9",
        f"arm-recomp-core-{CORE_COMMIT}.zip"),
    "toml": (
        "https://raw.githubusercontent.com/marzer/tomlplusplus/v3.4.0/toml.hpp",
        "6b5172ad4dd6519aec67b919181fa7a38a2234131e5b2afa232dfe444819783e",
        "toml.hpp"),
}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(name):
    url, expected, filename = PINS[name]
    destination = WORK / "downloads" / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        temporary = destination.with_suffix(destination.suffix + ".partial")
        with urllib.request.urlopen(url, timeout=120) as response:
            with temporary.open("wb") as output:
                shutil.copyfileobj(response, output)
        if digest(temporary) != expected:
            temporary.unlink()
            raise ValueError(f"SHA256 mismatch downloading {name}")
        temporary.rename(destination)
    if digest(destination) != expected:
        raise ValueError(f"SHA256 mismatch: {destination}; not overwritten")
    print(f"Verified {name}: {expected}")
    return destination


def extract(archive_path, destination, prefix=""):
    """Extract only regular files, preserving license files, without traversal."""
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        for item in archive.infolist():
            if not item.filename.startswith(prefix):
                raise ValueError("Unexpected archive prefix")
            relative = item.filename[len(prefix):]
            if not relative or item.is_dir():
                continue
            if ((item.external_attr >> 16) & 0o170000) == 0o120000:
                raise ValueError("Archive symlinks are not supported")
            target = (destination / relative).resolve()
            if not target.is_relative_to(destination):
                raise ValueError("Archive path traversal rejected")
            target.parent.mkdir(parents=True, exist_ok=True)
            data = archive.read(item)
            if target.exists():
                if target.read_bytes() != data:
                    raise ValueError(f"Existing dependency differs; not overwritten: {target}")
            else:
                target.write_bytes(data)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("component", choices=("ndspy", "host", "all"), nargs="?", default="ndspy")
    args = parser.parse_args(argv)
    if args.component in ("ndspy", "all"):
        # Pure Python wheel can be imported directly; its GPL license remains in it.
        print(f"ndspy wheel: {fetch('ndspy')}")
    if args.component in ("host", "all"):
        zig = fetch("zig")
        extract(zig, WORK / "tools/zig-0.15.2")
        source = WORK / "sources" / f"ndsrecomp-{NDS_COMMIT}"
        extract(fetch("ndsrecomp"), source, f"ndsrecomp-{NDS_COMMIT}/")
        extract(fetch("core"), source / "external/arm-recomp-core", f"arm-recomp-core-{CORE_COMMIT}/")
        header = WORK / "tools/tomlplusplus-3.4.0/toml.hpp"
        header.parent.mkdir(parents=True, exist_ok=True)
        data = fetch("toml").read_bytes()
        if header.exists() and header.read_bytes() != data:
            raise ValueError(f"Existing toml header differs: {header}")
        header.write_bytes(data)
        print(f"Host dependencies ready: {source}")
    record = {name: {"url": pin[0], "sha256": pin[1]} for name, pin in PINS.items()}
    (WORK / "dependency-bootstrap-pins.json").write_text(json.dumps(record, indent=2) + "\n")


if __name__ == "__main__":
    main()
