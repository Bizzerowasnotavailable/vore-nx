# Architecture and milestones

## Public/private boundary

The public NRO links only original cartridge preparation code and libnx/C++
runtime code. It has no ROMFS, game icon, Nintendo BIOS/firmware, translated game
banks, or game data. The public package is assembled by an explicit file
allowlist, not by archiving the workspace or Git working directory.

The user supplies `sdmc:/switch/vore-nx/rom.nds`. SHA-256 identifies the exact
supported image. All extracted material stays in a user-private directory:

```text
switch/vore-nx/data/<rom-sha256>/
  manifest.tsv        version, identity, offsets, sizes, addresses, file hashes
  header.bin          512-byte cartridge header
  arm9.bin            original raw main executable (not necessarily unpacked)
  arm7.bin            original raw main executable
  fnt.bin, fat.bin    raw NitroFS tables
  overlays9.bin       raw ARM9 overlay descriptors
  overlays7.bin       raw ARM7 overlay descriptors (possibly empty)
  file_000000.bin ... FAT payloads, including overlays and game assets
```

Numeric FAT names are deliberate: untrusted cartridge filenames never become
host filesystem paths. FNT is preserved for a future read-only virtual NitroFS
adapter. This is an extraction of the main images, tables and FAT files, **not a
lossless cartridge reconstruction**; card commands may still require the original
ROM. Empty files are preserved. Compression is not silently guessed or modified.

The extractor validates header CRC16, bounds using 64-bit arithmetic, main CPU
load/entry ranges, FAT structure, overlay file references and memory spans. It
streams hashing/copying through 64 KiB buffers. The exact hash gate is mandatory
for installation; structural inspection of other dumps is not support for them.
The manifest includes a separate SHA-256 for every extracted segment. Output is
staged and the source is hashed again before a directory rename commits it.
This is not a power-loss durability guarantee; stale `.partial` directories from
an abrupt shutdown need to be moved aside manually. Existing installations are
not overwritten or assumed verified. No network service or telemetry is used.

## Static recompilation: not yet integrated

The intended development chain is:

1. Exact-ROM validation and private extraction (**implemented**).
2. Inspect startup/module parameters and decompress executable code where needed
   (**ARM9 preparation implemented and checked against footer/SDK metadata**).
3. Generate private ARM9/ARM7 main and overlay banks with ndsrecomp and live-byte
   validation (**implemented and driven by runtime coverage**). Discover actual
   ARM/Thumb entry points; do not decode all data.
4. Cross-compile C banks to AArch64 and integrate a Switch hardware runtime
   (**AArch64 objects built; desktop runtime boots; no Switch runtime yet**).
5. Validate dual-CPU bus timing, IPC, interrupts, DMA, card/save SPI, 2D/3D video,
   audio, touch, microphone, and persistence against observed game behavior.
6. Test real progression; only then call it playable.

As of the latest private milestone, a locally built ndsrecomp 0.6.10 desktop
runner with coverage-derived BIS banks and BSD-licensed FreeBIOS banks boots this
ROM through the animated title, save-file selection, Toad Town exploration and
in-game dialogue. Scripted Start/A/D-pad input was verified against captured
frames; both screens render. This is desktop execution evidence only. The public
Switch NRO still contains no runtime, and the private runner is not a
distributable artifact.

Bank selection is not hand-written. A scripted play session records which code
the interpreter had to execute; `ingest_coverage_manifests.py` resolves those
pages back to the cartridge images, reports modules running at undeclared load
bases, and emits per-module entry-point seeds. `tools/private/build_banks.py`
then recompiles the main images, the overlays that were actually resident, the
relocated ARM7 aliases and the runtime-materialized pages, every bank with
live-byte validation. One such iteration moved a scripted Toad Town session from
0.3% to 92% ARM9 dispatch hits (83% on the ARM7), and interactive desktop
throughput from 34% to above 100% of DS speed.

Runtime coverage is now driven by measurement rather than guesswork: the
remaining interpreted code is whatever the recorded sessions never reached, plus
code whose live bytes no longer match any generated image (revised overlays, and
RAM the game rewrites). Residual interpretation in a scripted session after the
coverage iteration is small: about 2.5 million ARM9 instructions across roughly
164,000 interpreter entries, i.e. short stubs rather than whole subsystems.
A Switch port must still either generate those banks offline into a private,
ROM-owner-built NRO or ship an interpreter-only runtime that reads the user's ROM
and includes only BSD-licensed FreeBIOS banks.

Extracted binaries and emitted C are private inputs, never public source. The
upstream static dispatcher includes original guest-byte validation arrays.
Removing textures/music does not make such a binary free of Nintendo code.
Consequently the shipped installer currently cannot run the game. A future
playable cartridge-free public NRO needs either an independently implemented
runtime/module-loading strategy with user-built local code, or an independently
authored replacement for game logic. Requiring users to build banks locally is
different from shipping a publicly distributable playable static binary.

Bank generation currently emits 9,997 ARM9 and 1,756 ARM7 functions for the main
images, plus 6 overlay banks and 2 relocated ARM7 alias banks; the whole set is
about 200 MB of generated C and compiles to a private runner in a few minutes.
Unresolved indirect-site counts remain in the main images, in addition to the
135 overlays no recorded session has loaded and any runtime-materialized code.
These are discovery counts, not percentages of game coverage. See
[AOT.md](AOT.md) for reproduction.

No interpreter/emulator wrapper is presented as a completed static port. A
successful bank emission or AArch64 compilation alone does not prove booting,
timing correctness, or playable coverage.

## Current dependency situation

The supplied ndsrecomp archive is v0.6.10. Its `external/arm-recomp-core`
submodule was absent and toml++ needed staging. The explicit bootstrap now
fetches a complete pinned private toolchain without editing that supplied tree.
Host generation requires a host C++20 compiler, not the devkitA64 target compiler.
The desktop cartridge tool here is independent of ndsrecomp and requires only C++17.

REA's connected server reported Ghidra unavailable (`GHIDRA_INSTALL_DIR` not set).
No Ghidra decompilation or runtime gameplay observation has been established.
Tool availability and source inspection are not reverse-engineering evidence
for specific game behavior.
