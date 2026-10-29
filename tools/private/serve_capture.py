#!/usr/bin/env python3
"""Drive the private ndsrecomp runner over its debug server and dump frames.

Private local tooling only: it launches the self-built runner against the
user-supplied ROM, advances emulated cycles, and writes PNG captures of both
DS screens for visual inspection. Nothing here is published.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import struct
import subprocess
import sys
import time
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
# Private working directory: the tree holding the self-built runner, the
# generated banks and the coverage captures. It is deliberately outside the
# published source tree, so it is an explicit input rather than an assumption.
LOCAL = os.environ.get("VORE_WORK") or os.path.dirname(HERE)
ROOT = os.path.dirname(LOCAL)
RUNNER = os.environ.get("VORE_RUNNER") or os.path.join(
    LOCAL, "runner-build", "nds_runner.exe")
ROM = os.environ.get("VORE_ROM") or os.path.join(ROOT, "rom.nds")


class Server:
    def __init__(self, port: int):
        self.port = port
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=120.0)
        self.f = self.sock.makefile("rwb")

    def cmd(self, **kw) -> dict:
        line = json.dumps(kw).encode() + b"\n"
        self.f.write(line)
        self.f.flush()
        resp = self.f.readline()
        if not resp:
            raise RuntimeError("server closed the connection")
        return json.loads(resp)

    def cmd_raw_framebuffer(self, engine: str = "A"):
        """Fetch one DS screen as raw RGB bytes (no hex inflation).

        The runner answers `framebuffer_raw` with a JSON header line followed
        by width*height*3 bytes, which is several times cheaper than the JSON
        hex form for interactive use.
        """
        line = json.dumps({"cmd": "framebuffer_raw", "engine": engine}).encode()
        self.f.write(line + b"\n")
        self.f.flush()
        header = self.f.readline()
        if not header:
            raise RuntimeError("server closed the connection")
        meta = json.loads(header)
        if "raw" not in meta:
            raise RuntimeError(f"raw framebuffer failed: {meta}")
        need = int(meta["raw"])
        data = self.f.read(need)
        if len(data) != need:
            raise RuntimeError("short raw framebuffer read")
        return meta.get("w", 256), meta.get("h", 192), data

    def close(self):
        try:
            self.f.close()
        finally:
            self.sock.close()


def write_png(path: str, width: int, height: int, rgb: bytes, scale: int = 2):
    stride = width * 3
    rows = []
    for y in range(height):
        row = rgb[y * stride:(y + 1) * stride]
        if scale > 1:
            row = b"".join(row[i:i + 3] * scale for i in range(0, stride, 3))
        for _ in range(scale):
            rows.append(b"\x00" + row)
    raw = b"".join(rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", width * scale, height * scale, 8, 2, 0, 0, 0)
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
        fh.write(chunk(b"IHDR", ihdr))
        fh.write(chunk(b"IDAT", zlib.compress(raw, 6)))
        fh.write(chunk(b"IEND", b""))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycles", type=int, default=200_000_000,
                    help="ARM9 cycle target before capture")
    ap.add_argument("--step", type=int, default=4_000_000,
                    help="rounds per serve command")
    ap.add_argument("--port", type=int, default=19842)
    ap.add_argument("--out", default=os.path.join(LOCAL, "captures"))
    ap.add_argument("--shots", type=int, default=3,
                    help="number of captures spread across the run")
    ap.add_argument("--boot", default="direct")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    log_path = os.path.join(LOCAL, "serve.log")
    log = open(log_path, "wb")
    cmd = [
        RUNNER, os.path.join(LOCAL, "runner-build"),
        str(args.cycles),
        "--rom", ROM,
        "--freebios",
        "--boot", args.boot,
        "--generated-firmware",
        "--no-save",
        "--diagnostics", "off",
        "--network", "off",
        "--serve",
        "--port", str(args.port),
    ]
    env = dict(os.environ)
    env["NDS_HOSTPROF"] = "0"
    proc = subprocess.Popen(cmd, cwd=os.path.join(LOCAL, "runner-build"),
                            stdout=log, stderr=subprocess.STDOUT, env=env)
    try:
        deadline = time.time() + 60
        while True:
            try:
                srv = Server(args.port)
                break
            except OSError:
                if time.time() > deadline:
                    raise
                if proc.poll() is not None:
                    raise RuntimeError(f"runner exited rc={proc.returncode}")
                time.sleep(0.25)

        print("ping:", srv.cmd(cmd="ping"))
        targets = [args.cycles * (i + 1) // (args.shots + 1)
                   for i in range(args.shots)] + [args.cycles]
        for idx, target in enumerate(targets):
            while True:
                st = srv.cmd(cmd="run_cycles", arm9=target)
                if st.get("reached"):
                    break
                if st.get("cycles", [0])[0] <= 0:
                    raise RuntimeError(f"run stalled: {st}")
                print("  ..", st["cycles"])
            regs = srv.cmd(cmd="regs")
            print(f"[shot {idx}] arm9={st['cycles'][0]} arm7={st['cycles'][1]}")
            print("  regs:", json.dumps(regs)[:400])
            for engine in ("A", "B"):
                fb = srv.cmd(cmd="framebuffer", engine=engine)
                if "rgb" not in fb:
                    print("  framebuffer", engine, fb)
                    continue
                rgb = bytes.fromhex(fb["rgb"])
                path = os.path.join(args.out, f"shot{idx}_{engine}.png")
                write_png(path, fb["w"], fb["h"], rgb)
                nonblack = sum(1 for i in range(0, len(rgb), 3)
                               if rgb[i] or rgb[i + 1] or rgb[i + 2])
                print(f"  {path} {fb['w']}x{fb['h']} nonblack={nonblack}")
            dig = srv.cmd(cmd="frame_digests")
            print("  digests:", json.dumps(dig)[:300])
        srv.cmd(cmd="frontend_exit")
        srv.close()
    finally:
        log.close()
        if proc.poll() is None:
            proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
