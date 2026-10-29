#!/usr/bin/env python3
"""Measure interactive throughput of the private desktop runtime.

Boots the runner in serve mode, advances it frame by frame exactly the way the
Tk player does (1.12M ARM9 cycles per step, then reads both framebuffers), and
reports effective DS frames per second. Private local tooling only.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from serve_capture import LOCAL, ROM, RUNNER, Server  # noqa: E402

FRAME = 1_120_590


def main() -> int:
    boot = int(sys.argv[1]) if len(sys.argv) > 1 else 1_200_000_000
    steps = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    log = open(os.path.join(LOCAL, "perf-bench.log"), "wb")
    env = dict(os.environ)
    env["NDS_HOSTPROF"] = "0"
    proc = subprocess.Popen(
        [RUNNER, os.path.join(LOCAL, "runner-build"), "0",
         "--rom", ROM, "--freebios", "--boot", "direct",
         "--generated-firmware", "--no-save", "--diagnostics", "off",
         "--network", "off", "--serve", "--port", "19894"],
        cwd=os.path.join(LOCAL, "runner-build"),
        stdout=log, stderr=subprocess.STDOUT, env=env)
    try:
        deadline = time.time() + 60
        while True:
            try:
                srv = Server(19894)
                break
            except OSError:
                if proc.poll() is not None or time.time() > deadline:
                    print("runner did not start", file=sys.stderr)
                    return 1
                time.sleep(0.25)
        t0 = time.time()
        srv.cmd(cmd="run_cycles", arm9=boot)
        t1 = time.time()
        print(f"boot to {boot/1e6:.0f}M ARM9 cycles: {t1-t0:.2f}s "
              f"({boot/(t1-t0)/1e6:.1f}M cycles/s)")

        target = boot
        t0 = time.time()
        for _ in range(steps):
            target += FRAME
            srv.cmd(cmd="run_cycles", arm9=target)
            srv.cmd_raw_framebuffer("A")
            srv.cmd_raw_framebuffer("B")
        t1 = time.time()
        fps = steps / (t1 - t0)
        print(f"{steps} interactive frames in {t1-t0:.2f}s -> {fps:.1f} fps "
              f"({fps/59.826*100:.0f}% of DS real time)")
        srv.cmd(cmd="frontend_exit")
        return 0
    finally:
        log.close()
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    sys.exit(main())
