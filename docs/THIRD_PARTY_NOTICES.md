# Third-party notices

No Nintendo code, images, audio, BIOS or firmware are redistributed. "Asset-free"
means free of Nintendo game material, not free of all copyrighted software:
the NRO includes properly licensed open-source libraries.

## libnx (linked into the NRO)

Source: <https://github.com/switchbrew/libnx>

Copyright 2017-2018 libnx Authors

Permission to use, copy, modify, and/or distribute this software for any purpose
with or without fee is hereby granted, provided that the above copyright notice
and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR
OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
PERFORMANCE OF THIS SOFTWARE.

## devkitA64 runtime libraries (linked into the NRO)

- newlib: the collected notices are in [NEWLIB-LICENSE.md](NEWLIB-LICENSE.md).
  Source: <https://sourceware.org/newlib/>. The NRO build replaces two absolute
  upstream SDK builder paths in newlib assertion diagnostic strings with neutral
  basenames. These diagnostic-only replacements are **not part of original
  newlib**; no executable instructions are changed.
- GCC libgcc/libstdc++: GPLv3 with the GCC Runtime Library Exception 3.1.
  Full texts: [GPLv3](GPL_3_0.md) and [Runtime Library Exception](GCC_RUNTIME_EXCEPTION.md).
  Upstream exception: <https://www.gnu.org/licenses/gcc-exception-3.1.html>.
  Source/toolchain: <https://github.com/devkitPro/buildscripts> and
  <https://gcc.gnu.org/>. The exception permits eligible compiled applications
  to be distributed under independent terms; these libraries are not covered
  by this project's MIT license.

## Development tools, not part of the public NRO

ndsrecomp, arm-recomp-core, toml++, Zig, and optional analysis/decompression
tools retain their upstream licenses. Dependency source is fetched privately;
no tool's translated cartridge output belongs in a public release. See
[AOT.md](AOT.md) for the pinned toolchain workflow when available.

Eden and REA/Ghidra are external test/analysis tools, not bundled dependencies.
The cartridge parser and SHA-256 implementation here are independently authored
project code, not copied from a ROM or proprietary SDK.

## Experimental local runtime (not the installer release)

The optional `tools/private/build_switch_runtime.py` build links local ndsrecomp
runtime sources (MIT, Matthew Stanley), arm-recomp-core (MIT), FreeBIOS
(BSD-2-Clause), and vendored melonDS software-renderer sources
(GPL-3.0-or-later), in addition to libnx and the toolchain libraries above.
Their exact notices remain in the prerequisite checkouts. The combined runtime
binary is not covered solely by this repository's MIT license; distribution
requires the applicable GPL source/notices and a separate privacy/license audit.
No such runtime binary is published here. The optional title banks remain
ROM-derived private output regardless of open-source dependency licensing.
