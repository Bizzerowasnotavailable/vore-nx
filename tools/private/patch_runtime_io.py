#!/usr/bin/env python3
"""Stage the explicit microphone ADC extension; never edit the dependency tree."""
from pathlib import Path


def microphone_source(text):
    if "case 0x60: g_tsc_conv = vore::microphone::sample();" in text:
        return text
    include = '#include "io.h"'
    channel = "case 0x50: g_tsc_conv = g_tsc_x; break;"
    if text.count(include) != 1 or text.count(channel) != 1:
        raise ValueError("unsupported io.cpp microphone patch context; refusing to guess")
    return text.replace(include, include + '\n#include "runtime_microphone.hpp"').replace(
        channel, channel + "\n            case 0x60: g_tsc_conv = vore::microphone::sample(); break; // Microphone ADC")


def stage(source: Path, output: Path):
    text = microphone_source(source.read_text(encoding="utf-8"))
    if not output.exists() or output.read_text(encoding="utf-8") != text:
        output.write_text(text, encoding="utf-8", newline="\n")
