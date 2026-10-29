#!/usr/bin/env python3
"""Differential check: recompiled banks vs. the Tier-3 interpreter.

The generated banks are only worth having if they compute exactly what the
guest's own instructions compute. ndsrecomp's `force_tier3` command makes the
runtime interpret every instruction instead of dispatching to static banks, so
running the same deterministic input timeline twice -- once with banks, once
forced to the interpreter -- and comparing frame digests is a direct correctness
test of the generated code.

Both runs advance the ARM9 to identical absolute cycle targets, so the guest
timeline is the same in both; any digest difference is a bank/codegen defect,
not scheduling noise. Private tooling: it runs the user's own cartridge.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from serve_capture import LOCAL, ROM, RUNNER, Server  # noqa: E402
from collect_coverage import Session  # noqa: E402

PORT = 19897
CHECKPOINTS = 0  # filled in from --checkpoints


def timeline(sess: Session, boot: int, step: int, legs) -> list[str]:
    """Drive the recorded timeline and return one digest per checkpoint."""
    digests = []
    sess.run(boot)
    digests.append(digest_of(sess.srv))
    sess.tap("start", 12_000_000)
    sess.tap("a", 12_000_000)
    sess.tap("a", 12_000_000)
    for _ in range(5):
        sess.tap("a", 12_000_000)
    sess.run(600_000_000)
    digests.append(digest_of(sess.srv))
    for direction in legs:
        sess.keys({direction})
        sess.run(200_000_000)
        sess.keys(set())
        sess.run(step)
        sess.tap("a", 12_000_000)
        digests.append(digest_of(sess.srv))
    return digests


def digest_of(srv: Server) -> str:
    parts = []
    for engine in ("A", "B"):
        width, height, raw = srv.cmd_raw_framebuffer(engine)
        parts.append(f"{engine}:{width}x{height}:{hashlib.sha256(raw).hexdigest()}")
    return "|".join(parts)


def run_once(force_tier3: bool, port: int, boot: int, step: int, legs) -> list[str]:
    tag = "tier3" if force_tier3 else "banks"
    log_path = os.path.join(LOCAL, f"diff-{tag}.log")
    log = open(log_path, "wb")
    env = dict(os.environ)
    env["NDS_HOSTPROF"] = "0"
    env["NDS_DEEP_TRACE"] = "0"
    proc = subprocess.Popen(
        [RUNNER, os.path.join(LOCAL, "runner-build"), "0",
         "--rom", ROM, "--freebios", "--boot", "direct",
         "--generated-firmware", "--no-save", "--diagnostics", "off",
         "--network", "off", "--serve", "--port", str(port)],
        cwd=os.path.join(LOCAL, "runner-build"),
        stdout=log, stderr=subprocess.STDOUT, env=env)
    srv = None
    try:
        deadline = time.time() + 120
        while True:
            try:
                srv = Server(port)
                break
            except OSError:
                if proc.poll() is not None:
                    raise RuntimeError(f"{tag}: runner exited rc={proc.returncode}")
                if time.time() > deadline:
                    raise RuntimeError(f"{tag}: runner never opened the port")
                time.sleep(0.25)
        if force_tier3:
            print(f"[{tag}] force_tier3:",
                  srv.cmd(cmd="force_tier3", on=1))
        sess = Session(srv, step)
        digests = timeline(sess, boot, step, legs)
        stats = srv.cmd(cmd="static_coverage")
        print(f"[{tag}] tier3 stats:", json.dumps(stats))
        srv.cmd(cmd="frontend_exit")
        return digests
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


def main() -> int:
    boot = int(sys.argv[1]) if len(sys.argv) > 1 else 1_400_000_000
    step = 30_000_000
    legs = ["right", "up", "left", "down"]
    banked = run_once(False, PORT, boot, step, legs)
    reference = run_once(True, PORT + 1, boot, step, legs)
    mismatches = [i for i, (a, b) in enumerate(zip(banked, reference)) if a != b]
    report = dict(checkpoints=len(banked),
                  mismatches=mismatches,
                  banked=banked, interpreter=reference)
    out = os.path.join(LOCAL, "tmp", "diff-tier3.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
        handle.write("\n")
    print(f"{len(banked)} checkpoints, {len(mismatches)} mismatches: {mismatches}")
    return 0 if not mismatches else 1


if __name__ == "__main__":
    sys.exit(main())
