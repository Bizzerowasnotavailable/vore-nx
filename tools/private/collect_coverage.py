#!/usr/bin/env python3
"""Collect a Tier-3 coverage manifest from a scripted private play session.

Private local tooling only. It drives the self-built ndsrecomp runner over the
debug server against the user-supplied ROM: boots to the title screen, walks a
scripted input timeline into gameplay, and asks the runner to dump its Tier-3
coverage manifest. The manifest holds the guest's own executed code pages; it
is private evidence and must never be committed or published.

The manifest is what `ndsrecomp/tools/ingest_coverage_manifests.py` turns into
recompiler seeds, so this script is the first stage of the overlay bank
pipeline rather than a screenshot tool.

Deep trace is disabled (NDS_DEEP_TRACE=0) while `--diagnostics` stays on:
coverage capture lives in the Tier-3 interpreter, not in the per-access bus
ring, so this keeps the bus fast path engaged.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from serve_capture import LOCAL, ROM, RUNNER, Server, write_png  # noqa: E402

# Bit indices of the inactive-low key mask, from the runner's input path.
KEYS = {"a": 0, "b": 1, "select": 2, "start": 3, "right": 4, "left": 5,
        "up": 6, "down": 7, "r": 8, "l": 9}
IDLE = 0x3FF


def mask_for(held):
    m = IDLE
    for key in held:
        m &= ~(1 << KEYS[key])
    return m


class Session:
    def __init__(self, srv: Server, cycles_per_step: int):
        self.srv = srv
        self.target = 0
        self.cycles_per_step = cycles_per_step
        self.out_dir = None

    def run(self, cycles: int):
        """Advance the ARM9 to an absolute cycle target."""
        self.target += cycles
        while True:
            st = self.srv.cmd(cmd="run_cycles", arm9=self.target)
            if st.get("reached"):
                break
            if st.get("cycles", [0])[0] <= 0:
                raise RuntimeError(f"run stalled: {st}")
        return st

    def keys(self, held):
        return self.srv.cmd(cmd="keys", mask=mask_for(held))

    def tap(self, key: str, hold: int):
        """Press `key`, advance `hold` ARM9 cycles, release, settle a little."""
        self.keys({key})
        self.run(hold)
        self.keys(set())
        self.run(self.cycles_per_step)

    def shot(self, name: str):
        if not self.out_dir:
            return
        os.makedirs(self.out_dir, exist_ok=True)
        report = {}
        for engine in ("A", "B"):
            w, h, raw = self.srv.cmd_raw_framebuffer(engine)
            path = os.path.join(self.out_dir, f"{name}_{engine}.png")
            write_png(path, w, h, raw)
            nonblack = sum(1 for i in range(0, len(raw), 3)
                           if raw[i] or raw[i + 1] or raw[i + 2])
            report[engine] = dict(path=path, nonblack=nonblack)
        st = self.srv.cmd(cmd="scheduler_state")
        print(f"[shot] {name} {json.dumps(report)}")
        print(f"       cycles={st.get('cycles')} frames={st.get('frames')}")
        return report

    def coverage(self, path: str):
        res = self.srv.cmd(cmd="coverage_manifest", path=path)
        print(f"[coverage] {json.dumps(res)}")
        if not res.get("ok"):
            raise RuntimeError(f"coverage_manifest failed: {res}")
        return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=19895)
    ap.add_argument("--out", default=os.path.join(LOCAL, "coverage"))
    ap.add_argument("--shots", default=os.path.join(LOCAL, "captures", "cov"))
    ap.add_argument("--boot-cycles", type=int, default=1_400_000_000,
                    help="ARM9 cycles for firmware/BIOS boot to the title card")
    ap.add_argument("--step", type=int, default=30_000_000)
    ap.add_argument("--hold", type=int, default=12_000_000)
    ap.add_argument("--manifest", default="session")
    ap.add_argument("--scenario", choices=("reach", "sweep"), default="reach",
                    help="reach: scripted path into Toad Town; sweep: extra "
                         "movement/menu rounds for broader code coverage")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--leg", type=int, default=250_000_000,
                    help="ARM9 cycles per movement leg in the sweep scenario")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    manifest = os.path.join(args.out, f"{args.manifest}-coverage.json")
    log_path = os.path.join(args.out, f"{args.manifest}.log")
    log = open(log_path, "wb")
    env = dict(os.environ)
    env["NDS_HOSTPROF"] = "0"
    env["NDS_DEEP_TRACE"] = "0"
    cmd = [
        RUNNER, os.path.join(LOCAL, "runner-build"), "0",
        "--rom", ROM, "--freebios", "--boot", "direct",
        "--generated-firmware", "--no-save",
        "--diagnostics", "on", "--network", "off",
        "--serve", "--port", str(args.port),
    ]
    proc = subprocess.Popen(cmd, cwd=os.path.join(LOCAL, "runner-build"),
                            stdout=log, stderr=subprocess.STDOUT, env=env)
    srv = None
    try:
        deadline = time.time() + 120
        while True:
            try:
                srv = Server(args.port)
                break
            except OSError:
                if proc.poll() is not None:
                    raise RuntimeError(f"runner exited rc={proc.returncode}")
                if time.time() > deadline:
                    raise RuntimeError("runner did not open the debug port")
                time.sleep(0.25)

        sess = Session(srv, args.step)
        sess.out_dir = args.shots
        print("ping:", srv.cmd(cmd="ping"))

        t0 = time.time()
        sess.run(args.boot_cycles)
        print(f"boot to {args.boot_cycles} ARM9 cycles in {time.time() - t0:.1f}s")
        sess.shot("01-title")

        # Title card -> save-file screen. Start is what the earlier session
        # used; A also advances the logo card, so tap both.
        sess.tap("start", args.hold)
        sess.shot("02-after-start")
        sess.tap("a", args.hold)
        sess.shot("03-after-a")
        sess.tap("a", args.hold)
        sess.shot("04-after-a2")

        # File screen: five A presses started a new game in the earlier run.
        for i in range(5):
            sess.tap("a", args.hold)
        sess.shot("05-after-file-a")

        # Let the intro/scene load, then walk right for a while.
        sess.run(600_000_000)
        sess.shot("06-scene")
        sess.keys({"right"})
        sess.run(200_000_000)
        sess.shot("07-walking")
        sess.keys(set())
        sess.run(args.step)
        sess.shot("08-stop")

        # A few more A/B probes so menus, dialogue and combat entry contribute.
        for i in range(3):
            sess.tap("a", args.hold)
        sess.run(300_000_000)
        sess.shot("09-after-a3")
        sess.tap("b", args.hold)
        sess.run(300_000_000)
        sess.shot("10-after-b")

        if args.scenario == "sweep":
            # Broad sweep: the point is not a specific destination but reaching
            # menus, dialogue, transitions and any battle the area offers, so a
            # screenshot is taken after every leg to prove where the session
            # actually went.
            for round_index in range(args.rounds):
                for direction in ("right", "up", "left", "down"):
                    sess.keys({direction})
                    sess.run(args.leg)
                    sess.shot(f"r{round_index}-{direction}")
                    sess.keys(set())
                    sess.run(args.step)
                for i in range(4):
                    sess.tap("a", args.hold)
                    sess.run(args.step)
                sess.shot(f"r{round_index}-after-a")

        st = sess.srv.cmd(cmd="scheduler_state")
        print("final:", json.dumps(st))
        sess.coverage(manifest)
        srv.cmd(cmd="frontend_exit")
        return 0
    finally:
        log.close()
        if srv:
            try:
                srv.close()
            except Exception:
                pass
        if proc.poll() is None:
            proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
