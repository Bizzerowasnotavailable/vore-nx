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
   validation (**main banks emitted; overlays still metadata-only**). Discover
   actual ARM/Thumb entry points; do not decode all data.
4. Cross-compile C banks to AArch64 and integrate a Switch hardware runtime.
5. Validate dual-CPU bus timing, IPC, interrupts, DMA, card/save SPI, 2D/3D video,
   audio, touch, microphone, and persistence against observed game behavior.
6. Test real progression; only then call it playable.

Extracted binaries and emitted C are private inputs, never public source. The
upstream static dispatcher includes original guest-byte validation arrays.
Removing textures/music does not make such a binary free of Nintendo code.
Consequently the shipped installer currently cannot run the game. A future
playable cartridge-free public NRO needs either an independently implemented
runtime/module-loading strategy with user-built local code, or an independently
authored replacement for game logic. Requiring users to build banks locally is
different from shipping a publicly distributable playable static binary.

Main-bank generation currently emits 595 ARM9 and 1,416 ARM7 discovered functions;
all six C units compiled to private AArch64 relocatable objects. Unresolved
indirect-site counts are 24/32 respectively, in addition to 141 untranslated
ARM9 overlays and unknown runtime-materialized code. These are discovery counts,
not percentages of game coverage. See [AOT.md](AOT.md) for reproduction.

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
