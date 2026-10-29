#!/usr/bin/env python3
"""Stage a Switch hardware-counter profiler without modifying dependency files."""
from pathlib import Path


def clock_header(text):
    if "return armGetSystemTick();" in text:
        return text
    include = "#include <string>"
    anchor = "inline uint64_t tick_now() {\n#if defined(NDS_DISPATCH_TIMING_TSC)"
    if text.count(include) != 1 or text.count(anchor) != 1:
        raise ValueError("unknown dispatch_timing.h clock context")
    return text.replace(include, include + "\n#if defined(NDS_SWITCH) && defined(__aarch64__)\n"
        "#include <switch/arm/counter.h>\n#endif").replace(anchor,
        "inline uint64_t tick_now() {\n#if defined(NDS_SWITCH) && defined(__aarch64__)\n"
        "    return armGetSystemTick();\n#elif defined(NDS_DISPATCH_TIMING_TSC)")


def clock_source(text):
    if "static_cast<double>(armGetSystemTickFreq())" in text:
        return text
    anchor = "double measure_ns_per_tick() {\n#if defined(NDS_DISPATCH_TIMING_TSC)"
    if text.count(anchor) != 1:
        raise ValueError("unknown dispatch_timing.cpp calibration context")
    return text.replace(anchor, "double measure_ns_per_tick() {\n"
        "#if defined(NDS_SWITCH) && defined(__aarch64__)\n"
        "    return 1000000000.0 / static_cast<double>(armGetSystemTickFreq());\n"
        "#elif defined(NDS_DISPATCH_TIMING_TSC)")


def minimal_profiling_header(text, filename):
    if "VORE_MINIMAL_PROFILING" in text:
        return text
    if filename == "dispatch_timing.h":
        anchors = {
            "inline void nds_dispatch_tag(NdsDispatchClass cls) {": "return;",
            "explicit NdsDispatchRegion(int cpu) : cpu_(cpu & 1) {": "return;",
            "explicit NdsDispatchCacheRegion(int cpu) : cpu_(cpu & 1) {": "return;",
        }
    elif filename == "emu_profile.h":
        anchors = {
            "inline uint8_t nds_emu_enter(NdsEmuBucket bucket) {": "return NDS_EMU_INACTIVE;",
            "inline void nds_emu_exit(uint8_t prev) {": "return;",
            "    NdsEmuRound() {": "sampling_ = false; return;",
            "explicit NdsEmuBusRegion(uint32_t addr) {": "return;",
        }
    else:
        raise ValueError("unexpected profiling header")
    for anchor, early_return in anchors.items():
        if text.count(anchor) != 1:
            raise ValueError(f"unknown {filename} profiling context: {anchor}")
        text = text.replace(anchor, anchor + "\n#if defined(NDS_SWITCH) && VORE_MINIMAL_PROFILING\n    " +
                            early_return + "\n#endif")
    return text


def stage_runtime(source: Path, output: Path, patch_microphone, minimal=False):
    """Stage sibling headers too: quoted includes otherwise select original files."""
    output.mkdir(parents=True, exist_ok=True)
    for path in sorted(source.iterdir()):
        if not path.is_file() or path.suffix not in (".h", ".hpp", ".cpp"):
            continue
        text = path.read_text(encoding="utf-8")
        if path.name == "dispatch_timing.h": text = clock_header(text)
        if path.name == "dispatch_timing.cpp": text = clock_source(text)
        if path.name == "io.cpp": text = patch_microphone(text)
        if minimal and path.name in ("dispatch_timing.h", "emu_profile.h"):
            text = minimal_profiling_header(text, path.name)
        target = output / path.name
        if not target.exists() or target.read_text(encoding="utf-8") != text:
            target.write_text(text, encoding="utf-8", newline="\n")
