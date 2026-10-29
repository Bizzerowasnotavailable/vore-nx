#!/usr/bin/env python3
"""One repeatable playability measurement for the private desktop runtime.

Boots the runner, plays a fixed input timeline into Toad Town, and reports the
numbers that say whether the static banks actually replaced interpreted
execution:

  * boot throughput (ARM9 cycles/second) to the title card,
  * Tier-3 interpreter entries and instructions, before vs. after the scripted
    session, per CPU -- the quantity static recompilation exists to remove,
  * dispatcher composition (cache hits, slow lookups, slice yields),
  * interactive throughput with the framebuffer read back every frame.

Private local tooling: it runs the user's own cartridge through the user's own
build. Nothing here is published.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from serve_capture import LOCAL, ROM, RUNNER, Server, write_png  # noqa: E402
from collect_coverage import Session  # noqa: E402

FRAME = 1_120_590
PORT = 19896


def shots(srv: Server, session: Session, out_dir: str | None, name: str) -> dict:
    """Save both DS screens when a shot directory is supplied."""
    if not out_dir:
        return {}
    os.makedirs(out_dir, exist_ok=True)
    report = {}
    for engine in ("A", "B"):
        width, height, raw = srv.cmd_raw_framebuffer(engine)
        path = os.path.join(out_dir, f"{name}_{engine}.png")
        write_png(path, width, height, raw)
        report[engine] = dict(path=path,
                              nonblack=sum(1 for i in range(0, len(raw), 3)
                                           if raw[i] or raw[i + 1] or raw[i + 2]))
    return report


def snapshot(srv: Server) -> dict:
    return dict(tier3=srv.cmd(cmd="static_coverage"),
                dispatch=srv.cmd(cmd="dispatch_stats"))


def delta(a: dict, b: dict) -> dict:
    out = {}
    for section in ("tier3", "dispatch"):
        for key, value in b[section].items():
            if isinstance(value, dict):
                for inner, count in value.items():
                    if isinstance(count, (int, float)) and inner in a[section].get(key, {}):
                        out[f"{section}.{key}.{inner}"] = count - a[section][key][inner]
            elif isinstance(value, (int, float)) and key in a[section]:
                out[f"{section}.{key}"] = value - a[section][key]
    return out


def blocked(measured: dict) -> dict:
    """Turn raw deltas into the ratios that describe playability."""
    t3_9 = measured.get("tier3.tier3_insns9", 0)
    t3_7 = measured.get("tier3.tier3_insns7", 0)
    e9 = measured.get("tier3.tier3_entries9", 0)
    e7 = measured.get("tier3.tier3_entries7", 0)
    summary = dict(
        tier3_instructions_arm9=t3_9,
        tier3_instructions_arm7=t3_7,
        tier3_instructions_total=t3_9 + t3_7,
        tier3_entries_arm9=e9,
        tier3_entries_arm7=e7,
        tier3_entry_size_arm9=round(t3_9 / e9, 2) if e9 else None,
        tier3_entry_size_arm7=round(t3_7 / e7, 2) if e7 else None,
    )
    for cpu in ("arm9", "arm7"):
        hits = measured.get(f"dispatch.{cpu}.cache_hit", 0)
        absent = measured.get(f"dispatch.{cpu}.cache_hit_absent", 0)
        total = hits + absent
        summary[f"static_lookup_share_{cpu}"] = (
            round(hits / total, 4) if total else None)
        summary[f"lookups_{cpu}"] = total
        summary[f"static_hits_{cpu}"] = hits
        summary[f"absent_lookups_{cpu}"] = absent
    return summary


def main() -> int:
    boot = int(sys.argv[1]) if len(sys.argv) > 1 else 1_400_000_000
    steps = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    out_path = sys.argv[3] if len(sys.argv) > 3 else None
    shot_dir = (sys.argv[4] if len(sys.argv) > 4
                else os.path.join(LOCAL, "captures", "measure"))
    log_path = os.path.join(LOCAL, "measure-play.log")
    log = open(log_path, "wb")
    env = dict(os.environ)
    env["NDS_HOSTPROF"] = "0"
    env["NDS_DEEP_TRACE"] = "0"
    cmd = [RUNNER, os.path.join(LOCAL, "runner-build"), "0",
           "--rom", ROM, "--freebios", "--boot", "direct",
           "--generated-firmware", "--no-save", "--diagnostics", "off",
           "--network", "off", "--serve", "--port", str(PORT)]
    proc = subprocess.Popen(cmd, cwd=os.path.join(LOCAL, "runner-build"),
                            stdout=log, stderr=subprocess.STDOUT, env=env)
    srv = None
    report = dict(boot_cycles=boot)
    try:
        deadline = time.time() + 120
        while True:
            try:
                srv = Server(PORT)
                break
            except OSError:
                if proc.poll() is not None:
                    print(f"runner exited rc={proc.returncode}", file=sys.stderr)
                    return 1
                if time.time() > deadline:
                    print("runner never opened the debug port", file=sys.stderr)
                    return 1
                time.sleep(0.25)

        sess = Session(srv, 30_000_000)
        t0 = time.time()
        sess.run(boot)
        boot_seconds = time.time() - t0
        report["boot_seconds"] = round(boot_seconds, 2)
        report["boot_cycles_per_second"] = round(boot / boot_seconds / 1e6, 2)
        print(f"boot: {boot/1e6:.0f}M cycles in {boot_seconds:.2f}s "
              f"({report['boot_cycles_per_second']:.1f}M cycles/s)")

        before = snapshot(srv)
        report["title_shot"] = shots(srv, sess, shot_dir, "01-title")

        # Fixed timeline, matching the session that first reached Toad Town:
        # title card -> logo -> file screen -> new game -> walk right.
        sess.tap("start", 12_000_000)
        sess.tap("a", 12_000_000)
        sess.tap("a", 12_000_000)
        report["menu_shot"] = shots(srv, sess, shot_dir, "02-file-screen")
        for _ in range(5):
            sess.tap("a", 12_000_000)
        sess.run(600_000_000)
        report["scene_shot"] = shots(srv, sess, shot_dir, "03-scene")
        sess.keys({"right"})
        sess.run(200_000_000)
        sess.keys(set())
        sess.run(30_000_000)
        report["play_shot"] = shots(srv, sess, shot_dir, "04-walking")
        for _ in range(3):
            sess.tap("a", 12_000_000)
        sess.run(300_000_000)

        mid = snapshot(srv)
        report["session"] = delta(before, mid)
        report["session_playability"] = blocked(report["session"])

        # Interactive throughput with per-frame framebuffer readback, exactly
        # how the Tk player drives the runner.
        target = sess.target
        t0 = time.time()
        for _ in range(steps):
            target += FRAME
            srv.cmd(cmd="run_cycles", arm9=target)
            srv.cmd_raw_framebuffer("A")
            srv.cmd_raw_framebuffer("B")
        elapsed = time.time() - t0
        fps = steps / elapsed
        report["interactive_fps"] = round(fps, 1)
        report["percent_of_ds_realtime"] = round(fps / 59.826 * 100, 0)

        after = snapshot(srv)
        report["total"] = delta(before, after)
        report["total_playability"] = blocked(report["total"])
        print(json.dumps({k: report[k] for k in
                          ("boot_seconds", "boot_cycles_per_second",
                           "interactive_fps", "percent_of_ds_realtime")},
                         indent=2))
        print(json.dumps(report["session_playability"], indent=2))
        srv.cmd(cmd="frontend_exit")
        return 0
    finally:
        if out_path and srv:
            with open(out_path, "w", encoding="utf-8") as handle:
                json.dump(report, handle, indent=2)
                handle.write("\n")
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
