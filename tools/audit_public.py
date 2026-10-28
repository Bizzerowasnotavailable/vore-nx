#!/usr/bin/env python3
"""Scan the publication allowlist without reading Git credentials or private data."""
import os
from pathlib import Path
import re
import subprocess
import sys

from package_release import ROOT, audit_nro, source_paths

SECRET_PATTERNS = (
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{24,}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{24,}"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----\r?\n[A-Za-z0-9+/=\r\n]{32,}"),
    re.compile(rb"https?://[^\s/:@]+:[^\s/@]+@"),
)


def main():
    paths = source_paths()
    nro = ROOT / "vore-nx.nro"
    if nro.exists():
        audit_nro(nro.read_bytes())
    findings = []
    username = os.environ.get("USERNAME", "")
    private_home_markers = []
    if username:
        for prefix in ("C:/Users/", "C:\\Users\\", "/home/", "/Users/"):
            private_home_markers.append((prefix + username).encode().lower())
    for path in paths:
        data = path.read_bytes()
        if any(pattern.search(data) for pattern in SECRET_PATTERNS):
            findings.append(f"possible credential in {path.relative_to(ROOT)} (value suppressed)")
        if any(marker in data.lower() for marker in private_home_markers):
            findings.append(f"local personal home path in {path.relative_to(ROOT)}")
    # Check tracked files by names only. Never read .git/config or ignored inputs.
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True).stdout
    allowed = {p.relative_to(ROOT).as_posix() for p in paths}
    for raw in tracked.split(b"\x00"):
        if raw:
            name = raw.decode("utf-8")
            if name not in allowed:
                findings.append(f"tracked path outside public source allowlist: {name}")
    if findings:
        print("PUBLICATION BLOCKED:\n" + "\n".join(findings))
        return 1
    print(f"Public audit passed: {len(paths)} source/license/workflow files; no private inputs read.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
