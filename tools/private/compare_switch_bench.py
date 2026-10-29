#!/usr/bin/env python3
"""Compare completed Switch benchmarks without exporting game images/logs."""
import argparse
import json
from pathlib import Path
import re
import statistics

CHECKPOINT = re.compile(r"checkpoint frame=(\d+) target=(\d+) pixels64=([0-9A-F]{16})/([0-9A-F]{16})")
PERF = re.compile(r"performance: ([0-9.]+) guest frames/s scheduler=([0-9.]+)ms present=([0-9.]+)ms")


def parse(text):
    if "benchmark: complete" not in text or "fatal:" in text:
        raise ValueError("benchmark incomplete or fatal error recorded")
    checkpoints, intervals = {}, {}
    pending = None
    for line in text.splitlines():
        perf = PERF.search(line)
        if perf: pending = tuple(float(x) for x in perf.groups())
        point = CHECKPOINT.search(line)
        if point:
            frame, target, top, bottom = point.groups()
            frame = int(frame)
            if frame in checkpoints or pending is None:
                raise ValueError("duplicate checkpoint or missing timing interval")
            checkpoints[frame] = (int(target), top, bottom)
            intervals[frame] = pending
            pending = None
    if not checkpoints: raise ValueError("no framebuffer checkpoints")
    return checkpoints, intervals


def compare(reference, candidate, min_frame=600):
    left, before = parse(reference)
    right, after = parse(candidate)
    if left.keys() != right.keys(): raise ValueError("checkpoint sets differ")
    mismatches = [frame for frame in left if left[frame] != right[frame]]
    frames = [frame for frame in left if frame >= min_frame]
    if not frames: raise ValueError("no timing intervals beyond warm-up")
    def summary(values):
        return {"median_guest_fps": statistics.median(values[f][0] for f in frames),
                "median_scheduler_ms": statistics.median(values[f][1] for f in frames),
                "median_present_ms": statistics.median(values[f][2] for f in frames)}
    result = {"checkpoints": len(left), "mismatches": mismatches,
              "reference": summary(before), "candidate": summary(after),
              "timing_min_frame": min_frame}
    result["median_fps_ratio"] = result["candidate"]["median_guest_fps"] / result["reference"]["median_guest_fps"]
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("reference", type=Path)
    ap.add_argument("candidate", type=Path)
    ap.add_argument("--min-frame", type=int, default=600)
    args = ap.parse_args()
    report = compare(args.reference.read_text(encoding="utf-8-sig"),
                     args.candidate.read_text(encoding="utf-8-sig"), args.min_frame)
    print(json.dumps(report, indent=2))
    return int(bool(report["mismatches"]))


if __name__ == "__main__":
    raise SystemExit(main())
