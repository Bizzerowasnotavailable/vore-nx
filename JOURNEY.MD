# Development journey

## 2026-10-28 — Initial assessment

- Existing repository: initial commit and a two-line README only. No earlier
  journey, source, generated banks, or build artifacts were present.
- Available: ndsrecomp 0.6.10 source, devkitPro/devkitA64/libnx, Eden for Windows,
  and one locally supplied 128 MiB DS cartridge image.
- Local image identity: European revision 0, game code `CLJP`, SHA-256
  `4d8a3ffa13ad525db85e596d576675860a816aa77560ca87c4505451c172c60b`.
  Hashes/addresses are metadata; cartridge bytes must never be committed.
- ndsrecomp has no turnkey Switch frontend; its generated dispatch tables embed
  original instruction bytes as well as translated code. Do not redistribute
  generated banks in an allegedly cartridge-free release.
- Goal for the first milestone: an original-code Switch NRO installer, defensive
  streaming cartridge parser/extractor, desktop tests, private AOT generation,
  and honest compatibility reporting. This milestone is **not a playable port**.

## Completion gates

- [x] Desktop parser/extractor tested with synthetic fixtures and the local ROM.
- [x] Asset-free NRO cross-compiled with devkitA64.
- [x] Eden smoke test recorded (or exact blocker documented).
- [x] ARM9/ARM7 static banks emitted privately and limitations recorded.
- [x] Distribution allowlist checked; no cartridge bytes or personal data.
- [x] Private desktop ndsrecomp runner boots the game to the title screen, save
  screen and Toad Town with scripted input (see the 2026-10-28 runtime section).
- [ ] Switch DS bus, CPU scheduler, IRQ/IPC, decompression/overlay banks,
  rendering, sound, input/touch/microphone, saves, and game progression tests.
- [ ] Future: game title screen, new game, both combat modes, giant battles,
  saving/loading, and ending independently verified.

No gameplay completion percentage is inferred from successful extraction or
compilation. Append measured results below as work progresses.

## 2026-10-28 — Cartridge-preparation milestone

- Implemented original C++17 parser, SHA-256, CRC16, streamed extraction,
  per-segment manifest, exact-ROM gate, cancel/rollback, and non-overwrite rules.
- Switch frontend: A verifies, X extracts, B cancels work, + exits. It explicitly
  says game execution is unavailable. NRO has NACP only: no icon or ROMFS.
- Cross-build succeeded with devkitA64 GCC 16.1.0 and the installed libnx.
  Build wrapper accounts for Python missing from the MSYS login PATH.
- Release audit caught two absolute **upstream toolchain builder** paths in
  prebuilt newlib assertion strings (not local user data). Added narrowly scoped,
  tested diagnostic-string redaction; offsets and executable code stay unchanged.
- Portable Zig 0.15.2 / Clang 20.1.2 host build succeeded without a system-wide
  compiler installation. ndsrecomp and its exact missing ARM-core gitlink were
  recovered privately; see AOT documentation for pins/reproduction.
- **260 synthetic C++ checks passed**, including hashing vectors/padding,
  malformed/truncated images, arithmetic overflows, FAT/overlay validation,
  cancellation, unsupported-identity rejection, and no-write behavior.
- **14 private integration checks passed**: actual-ROM identity, cancellation
  rollback, preserving pre-existing staging data, successful commit, all output
  files present, and duplicate-install refusal without touching existing data.
- Independently compared **237 extracted segments / 94,786,132 bytes** against
  original cartridge ranges and manifest SHA-256. Inventory: **230 FAT files,
  141 ARM9 overlays, zero ARM7 overlays**. No extracted bytes were published.
- Connected REA server reports Ghidra unavailable because `GHIDRA_INSTALL_DIR`
  is unset. No Ghidra session was opened, and no decompilation result is claimed.
  Local objdump corroborated an ARM startup at `0x02004800`; disassembly remains
  private. Header addresses alone do not establish subsequent game behavior.

### Eden test boundary

- Tested the provided `de7e6e01d4` Windows CLI in a separate private portable
  `user` directory; no user keys, firmware, saves or global settings were copied.
- Eden's log recognized/loaded **vore-nx ROM preparation**, then reported
  **failure to allocate 4096 MiB of backing memory** and an access violation
  (`0xC0000005`). CLI `--help` also faulted. No rendered app window was verified.
- Host had less than 4 GiB free virtual commit during the test; another existing
  user Eden instance was left untouched. The log is compatible with host memory
  pressure, but does not prove the only crash cause. No system/pagefile changes.
- Therefore NRO UI, controller handling and SD-card extraction are **cross-built
  but not runtime-validated**. Desktop extractor validation is separate evidence.
- Gameplay/title screen remains **not implemented**. No real Switch test yet.

### Region-metadata correction

The initial working interpretation incorrectly called `CLJP` Japanese. It is
European (`NTR-CLJP-EUR`); Japanese is `CLJJ`. Documentation was corrected against
the serial-code tables at [Data Crystal](https://datacrystal.tcrf.net/wiki/Mario_%26_Luigi:_Bowser%27s_Inside_Story)
and [MarioWiki](https://www.mariowiki.com/Mario_%26_Luigi:_Bowser%27s_Inside_Story).
The measured hash, game code, revision, extraction and identity gate were correct
throughout; no different ROM was selected or downloaded.

## 2026-10-28 — Private AOT milestone

- Added end-user reproducible `tools/bootstrap_host.py`, `tools/build_host.py`,
  and offline `tools/aot.py`; instructions and exact pins are in `docs/AOT.md`.
- Tested explicit bootstrap, host/recompiler builds, preparation, audit,
  generation and AArch64 object compilation. Downloads are pinned by SHA-256;
  no global compiler/decompressor installation is required.
- ARM9: raw **219,452 bytes**, expanded analysis **341,144 bytes**. Footer
  expansion **121,692 bytes**, unchanged **16,384-byte prefix**, expanded end
  matches the SDK autoload table. Pinned ndspy 4.2.0 decompresses privately.
  SDK compressed-end metadata is retained; the expanded file is **not** a
  replacement boot image. Two proven SDK copy aliases are declared and startup
  relocation simulation is disabled to avoid decompressing the analysis twice.
- ARM7: raw/prepared **160,036 bytes**, no recognized SDK/code-compression
  signature. Unchanged analysis input; relocation scan found two copy aliases.
- Main-bank audit and generation agree: **595 ARM9 functions / 24 unresolved
  indirect sites**, **1,416 ARM7 functions / 32 unresolved indirect sites**.
  Discovery is incomplete; counts are not game coverage percentages.
- Each bank has a verified header, two body shards and a nonempty dispatch table
  with live-byte validation. Body+dispatch output sizes: **3,951,632 bytes ARM9**,
  **10,577,294 bytes ARM7**. These C files contain Nintendo-derived code and stay
  exclusively under ignored `private/`; they are never linked into the release.
- All **six generated C translation units** compiled with devkitA64 GCC 16.1.0
  into verified ELF64 AArch64 relocatable objects, **21,490,280 bytes** in total.
  Matching runtime ABI headers were hash-verified. No runtime linking/execution.
- The explicit raw-startup-only fallback also emitted **46 ARM9 startup
  functions** without importing ndspy. It does not claim the compressed body.
- **141 ARM9 overlays remain descriptors only**: no guessed entries or coverage
  claim. Indirect callbacks and runtime-produced code need separate evidence.
- Added ROM-free GitHub CI, independent installation verifier, public-file
  privacy audit, deterministic allowlisted ZIP packaging, and licensed runtime
  notices. Private inputs, logs, C banks and objects are excluded.

### Final validation / release boundary

- Final host rebuild: **260 C++ synthetic checks passed**. Private integration
  run: **14 checks passed**. Independent installation verification confirmed
  all **237 segments / 94,786,132 bytes** against the source ROM and manifest.
- Final Python run: **32 tests, 31 passed / 1 skipped** (Windows did not permit
  the synthetic symlink test). No cartridge is needed for these tests.
- Independently re-checked every generated bank-file digest and all six private
  AArch64 object digests, sizes, ELF class, architecture and relocatable type.
- Initial v0.1.0 public NRO SHA-256:
  `c3e1d4064cab84981191af2db9e4a31c4dac94ffe6fef18aa03fc043f02c21f9`.
  Structural audit confirms NACP only, no icon/ROMFS/trailing payload, and no
  embedded local home paths or ROM-derived dispatch markers.
- Initial public release designation: **v0.1.0 — ROM preparation (NOT PLAYABLE)**.
  Only reviewed original source, licensed-library notices, the installer NRO
  and checksums belong in publication. Generated game banks are not included.
- Open work is unchanged: runtime/module strategy, overlay entry discovery,
  DS hardware backend, video/audio/input/save integration, real Switch testing,
  and actual game progression. This is partial progress toward the requested
  static port, not fulfillment of a playable-game milestone.

## 2026-10-28 — Linux CI portability follow-up (v0.1.1)

- Source and installer v0.1.0 were published after local tests and privacy checks.
- Linux GitHub CI caught GCC's `-Werror=ignored-attributes` on an attributed
  `fclose` function pointer used as a `unique_ptr` deleter. Windows Clang and
  devkitA64 had accepted it. Replaced it with a named RAII deleter; did not
  disable warnings or change file ownership/transaction semantics.
- Bumped to v0.1.1 rather than silently moving the already-published v0.1.0 tag.
  The old source/release is preserved. No new game runtime/playability claim.
- v0.1.1 local rebuild passed: **260 synthetic C++ checks**, **14 private-ROM
  integration checks**, all **237 segment** comparisons, and **31 Python passes /
  1 platform skip**. Source/license/workflow publication allowlist: **36 files**.
- v0.1.1 asset-free NRO SHA-256:
  `d19b00db5eb9ac14b0890c2c5496626bddfff40b9cfed17f21a5a847603b6e20`.
  GitHub Actions is the independent Linux CMake/CTest validation record for this
  follow-up; publication must wait for its code-fix run to pass.
- Independent Linux code-fix CI **passed**: [run 40711337926](https://github.com/Bizzerowasnotavailable/vore-nx/actions/runs/40711337926),
  validating CMake configuration/build, CTest, ROM-free Python tests, and the
  tracked-file privacy allowlist. v0.1.1 is approved for the same not-playable
  installer-only release boundary; this follow-up does not change gameplay.

## 2026-10-28 � Private desktop runtime boot and gameplay evidence

Status: **major private milestone, no public playability change.** The shipped
Switch NRO is still installer-only. A locally built desktop runner now executes
the game far enough to render its title screen and enter Toad Town with scripted
input. This section records measured evidence and its limits.

### Two concrete runner blockers fixed

- The generated runner registry gated every title bank behind
  `NDS_TITLE_ROM_SHA1`; the cache had an empty value, so the earlier "boot" ran
  without any BIS banks. Reconfiguring with the exact SHA-1
  `5f35bfbf79a0947740795dd770d99e8eea3ac85e` produced a registry that registers
  `bis_arm9_main` and `bis_arm7_main` for this exact ROM.
- The FreeBIOS/BIOS banks had been emitted with `--validate-live-bytes`. Their
  live-byte checks require write provenance, but immutable BIOS backings produced
  by `bus_load_arm7_bios` have no written-byte mask, so even a byte-perfect
  dispatch entry at the ARM7 SWI vector `0x00000008` was rejected. Regenerated
  both FreeBIOS banks without that flag, matching the upstream README's BIOS
  recipe. The next boot had no dispatch miss and both CPUs ran to the requested
  cycle budget.

### Execution evidence (headless, private)

- Runner: ndsrecomp 0.6.10 runner built with `NDS_SDL_BACKEND=NONE`, linked with
  the two private BIS main banks and the two FreeBIOS banks; boot path
  `--freebios --boot direct --generated-firmware`, no retail BIOS or firmware
  dump, network off, saves off.
- Both CPUs execute: at the 1.51 billion ARM9-cycle checkpoint the scheduler
  reports 1,337 vblank frames, and the ARM9 has taken 3,142 IRQs while the ARM7
  has taken 14,522. Earlier 10M- and 100M-cycle runs both completed without
  dispatch misses.
- Debug-server framebuffer reads show, in order: the animated title logo, the
  full logo card, the save-file screen with two "NEW FILE" stars, and Toad Town
  gameplay. Holding Right moved Mario and scrolled the camera; Luigi appears in
  the same sequence. Both 256x192 engines A/B produce non-black frames.
- Input path exercised end to end: inactive-low key masks for Start and A via the
  debug server, twice through the title and five times on the file screen until
  the new game starts. Touch injection was accepted by the server but did **not**
  select a file; the key path did.

### Coverage and performance honesty

- Static banks currently cover only the two main images. Most runtime execution
  after the game starts overlays and relocated code and falls back to ndsrecomp's
  Tier-3 interpreter. At the same checkpoint the counters were:
  ARM9 static cache hits **606,641** versus absent lookups **194,292,634**;
  ARM7 hits **1,568,553** versus absent **21,396,456**. This is execution
  evidence, not a completed static port, and the 141 ARM9 overlays are still
  untranslated.
- Throughput sample: a 100,000,000-ARM9-cycle headless boot completed in **2.8 s**
  wall time including process start (about 35M cycles/s, roughly half DS speed).
  That sample was taken before rendering pressure and is not an interactive
  performance claim.
- Not verified: an interactive windowed frontend, audio, saves, battles, touch
  or microphone input, long-session stability, and any Switch execution.

### Publication boundary

- Generated banks, captures, logs, object files and this runner build remain
  private. The captures visibly contain copyrighted game artwork and must not be
  committed or attached to releases.
- The public v0.1.1 NRO and source are unchanged: no game execution, no embedded
  assets, no Nintendo-derived code. Do not present this desktop result as a
  playable Switch release.
- Next technical steps: add an interactive desktop frontend to judge real-time
  play, then decide between (a) offline generation of the 141 overlays into a
  private Switch build for this ROM owner and (b) a shippable interpreter-only
  Switch runtime that reads the user's ROM and ships only BSD-licensed FreeBIOS
  banks.

## 2026-10-29 — Coverage-driven static banks: desktop passes DS speed

Status: **major private milestone, no public playability change.** The shipped
Switch NRO is still installer-only. The private desktop runner now executes most
of what a scripted session reaches as recompiled native code instead of Tier-3
interpreter work, and it runs faster than the DS itself on this host.

### The lever that was already available

ndsrecomp 0.6.10 already contained the whole Tier-3 coverage pipeline; nothing in
this repository used it. The runner records, per session, which guest code the
interpreter had to execute, `tools/ingest_coverage_manifests.py` resolves those
pages back to cartridge images and emits per-module entry-point seeds, and the
recompiler turns seeds into static banks. Connecting that pipeline to this
cartridge is what changed the numbers below.

New private tooling, now published as source only (no ROM-derived output):

- `tools/private/prepare_overlays.py` — decompresses all 141 ARM9 overlays from
  the cartridge into the image set the ingest tool expects (134 BLZ-compressed,
  7 raw, 4,467,008 bytes, 0 failures; 28 overlays are under 256 bytes).
- `tools/private/collect_coverage.py` — boots the runner headless, drives a
  scripted timeline, and asks the debug server for a coverage manifest. Supports
  a `sweep` scenario that adds movement and menu rounds for broader reach.
- `tools/private/build_banks.py` — seeds to banks: main images re-seeded from
  coverage, overlays compiled at their own load address, relocated ARM7 aliases,
  and the runtime-materialized page banks; `--validate-live-bytes` on every one.
- `tools/private/gen_switch_registry.py` — generates the AArch64 build's bank
  registration table from a bank directory (the desktop runner has CMake do
  this; the Switch compile script does not).
- `tools/private/measure_play.py` — the repeatable measurement used below.
- `tools/private/play_tk.py` — interactive Tk window (keyboard + stylus) so the
  result can be judged by playing rather than by frame captures.

### What the coverage found

The first manifest (253 executed code pages from a scripted run into Toad Town)
resolved 210 pages to the cartridge and left 43 that exist nowhere in the ROM:

- The **ARM7 module runs from relocated copies** at `0x037F7DE4` and
  `0x027D076C`, while the only ARM7 bank was compiled at the header address
  `0x02380000` — 677 entry points of hot sound-driver code with no bank at all.
  The relocation scanner independently proved both copies
  (`0x0238021C -> 0x037F8000` size `0xF678`, `0x0238F894 -> 0x027E0000` size
  `0x17879`).
- Hot **ARM9 overlays**: ov004 (2,031 entry points), ov003 (1,218), ov006 (717),
  ov125 (626), ov000 (110), ov129 (161), plus 4,428 entry points in the main
  image that the finder never discovered.
- A block of **runtime-materialized ARM9 code** at `0x01FF8000` whose bytes match
  nothing in the ROM (the SDK autoload path rewrites it), reached over 800,000
  times per session from a handful of call sites.

### What was generated, in three iterations

| Iteration | Banks | Generated C | Contents |
|---|---|---|---|
| 1 | 10 | 190 MB | main ARM9/ARM7 re-seeded, 6 overlays, 2 ARM7 aliases |
| 2 | 45 | 201 MB | + 35 runtime-materialized ARM9 page banks from the same manifest |
| 3 | 51 | 210 MB | re-seeded from a second 8.2-billion-cycle sweep session |

Every bank is content-validated against the guest's live bytes at dispatch time,
so banks that share a load address (46 overlays load at `0x020CB440`) are safe:
only the image actually resident can validate. Banks fail closed — a wrong or
stale bank falls through to the interpreter instead of running incorrect code.

Function counts after iteration 1: `bis_arm9_main` 9,997 (was 595 with no
coverage input), `bis_ov004_arm9` 6,104, `bis_ov003_arm9` 3,073,
`bis_arm7_alias_037f7de4` 1,756, `bis_ov125_arm9` 1,619, `bis_ov006_arm9` 1,422,
`bis_arm7_main` 1,416, `bis_ov129_arm9` 312, `bis_ov000_arm9` 268,
`bis_arm7_alias_027d076c` 268.

### Measured effect (desktop, private)

Scripted session: boot to 1.4 billion ARM9 cycles, then Start/A/D-pad into Toad
Town, walk right, and three A presses. "Before" is the previously recorded
main-banks-only checkpoint from the 2026-10-28 section; the per-session figures
for iterations 2 and 3 come from `tools/private/measure_play.py`.

| Metric | Before (main banks only) | Iteration 2 | Iteration 3 |
|---|---|---|---|
| ARM9 dispatches resolving to recompiled code | 0.3% (606,641 / 194,899,275) | 91.8% | 92.5% |
| ARM7 dispatches resolving to recompiled code | 6.8% (1,568,553 / 22,965,009) | 82.7% | 100% |
| Tier-3 ARM9 instructions in the scripted session | not measured (most code interpreted) | 2,546,720 | 2,303,995 |
| Tier-3 ARM7 instructions in the scripted session | not measured | 652,474 | 0 |
| Interactive throughput (framebuffer readback every frame) | 20.4 fps (34% of DS) | 66.5 fps (111%) | 62.2 fps (104%) |
| Boot throughput to 1.4 billion ARM9 cycles | 50.8M cycles/s | 153.4M cycles/s | 132.9M cycles/s |

The residual interpretation is now short stubs — roughly 15 instructions per
interpreter entry over 154,000 entries — rather than whole subsystems.

### Differential validation of the generated code

Speed alone would be worthless if the banks changed behaviour, so the banks were
checked against the interpreter itself. The runner can force every instruction
through Tier-3 (`force_tier3`), which makes the same deterministic timeline
runnable twice — once with static banks, once fully interpreted — with both runs
advancing to identical absolute cycle targets. Six checkpoints (title card,
save-file screen, and one per movement leg) compared the framebuffers byte for
byte:

- **0 mismatches.** The interpreter reference pass executed 870.7 million ARM9
  and 90.7 million ARM7 instructions; the banked pass executed the same work as
  recompiled native code and fell through to the interpreter for 3.2 million
  ARM9 instructions (260,706 entries) and 10 ARM7 instructions.
- `tools/private/diff_tier3.py` performs this comparison. It is the correctness
  gate that a "fast" bank set has to pass, and it is the reason bank validation
  fails closed: a stale bank must fall back to the interpreter rather than run.

### Progression evidence

- A five-round sweep (8.2 billion ARM9 cycles in one session) walked into a Toad
  Town house and triggered an NPC dialogue; the text box rendered
  "You'll never grow up into a fine Toad with such bad behavior!" over the room
  with both sprites present. The session stayed alive and both screens kept
  rendering.
- Title card, save-file screen, Toad Town, camera scrolling, Mario/Luigi sprites
  and dialogue all render identically before and after the bank change, which is
  the check that the generated code is not merely fast but correct on these
  paths.
- Not verified: battles, giant battles, touch/microphone, audio, save/load,
  long-session stability beyond ~8 billion cycles, the ending, and any execution
  on Switch hardware.

### Build cost

About 210 MB of generated C in 51 banks compiles at `-O2` in **3.5–3.9 minutes**
with six parallel compiler processes (zig/Clang) and about 2 GB peak resident
memory; the linked private runner is 66 MB. A single 32 MB translation unit costs
about 98 seconds and 940 MB on its own, which is why the runner build is capped at
six jobs rather than eight.

### Publication boundary

- Banks, objects, the runner build, coverage manifests, captures and logs are all
  ROM-derived and stay ignored. Only the pipeline scripts and this record are
  published.
- The public v0.1.1 NRO is unchanged: no runtime, no cartridge content. The
  desktop runner is a development instrument, not a distributable artifact.
- Next technical steps: drive the scripted session into combat and menus to
  convert the remaining interpreted stubs, then either rebuild the private
  AArch64 NRO with this bank set for the ROM owner or pursue an interpreter-only
  Switch runtime that ships only BSD-licensed FreeBIOS banks.

## 2026-10-29 - Switch runtime: frames presented in Eden

The AArch64 platform layer now runs far enough to present frames under Eden.
This is a runtime milestone, not a playability claim: the presented frames are
black because the guest has not written VRAM during early boot, and the private
51-bank build has not been verified yet.

### Why the earlier private NRO never presented

That NRO was alive (one core at 100%, about 4.9 GB resident) but stayed on
Eden's "Launching..." screen for minutes. Two faults were found and fixed; only
the first is proven from the logs, and neither is proven to be the sole cause of
the missing present:

1. **The save flush could never succeed.** `nds_battery_save_write_atomic()`
   writes a `.tmp` file and renames it over the save. Horizon OS refuses to
   rename onto an existing file, so every flush failed, the cartridge backup
   stayed dirty, and the IO layer retried the whole 8 KiB write on every
   hardware frame. Eden's log recorded about 800 `RenameFile ... already exists`
   errors in four seconds, and a stale `bis.sav.tmp` was left on the SD card.
   The fallback now removes the destination and retries the rename once; on
   POSIX the first atomic rename still succeeds, so the fast path is unchanged.
   After the fix the temporary file disappears and the save is written once.
2. **There was no way to see where boot stopped.** A presenting applet has no
   console and Eden does not surface stdout, so a hang inside `scheduler_run()`
   was indistinguishable from a slow Tier-3 boot. The runtime now writes a
   timestamped milestone log to `sdmc:/switch/vore-nx/vore.log`: ROM read,
   firmware, bank registration, direct boot, first present, every 60th frame,
   and the ARM9/ARM7 PCs plus cycle counters whenever one DS frame takes longer
   than a second of wall time.

A third presentation defect was found by inspection while adding that logging:
`nds_gpu2d_framebuffer()` returns XRGB (`0xFFRRGGBB`), but libnx's default window
is `RGBA_8888`, whose in-memory bytes must be R,G,B,A. The original conversion
emitted BGRA, so a successful present would have shown every screen with red and
blue exchanged. `pack_rgba()` now emits `0xAABBGGRR`, and the framebuffer-begin
failure check compares the returned pointer instead of a `Result`.

### Measured, public (bank-free) build

Interpreter-only, so this isolates the platform layer from the generated banks:

```
[   0.105] rom read: 134217728 bytes
[   0.108] game code CLJP accepted
[   0.111] firmware generated: 131072 bytes
[   2.075] direct boot: starting
[   2.083] direct boot: done, first frame target 1120590
[   2.458] present: first frame drawn (1280x720)
[  37.320] frame 600: scheduler_run target 673474590
```

The first frame is presented 2.4 s after launch and the applet loop keeps
advancing (600 DS frames in 37 s, roughly 6 fps with every cartridge instruction
interpreted). Eden reports "0 FPS" in its own status bar, but the log and the
changing frame targets show the DS machine advancing; Eden's counter reflects
its presentation timing, not the guest's.

### AArch64 build cost for the 51-bank set

The bank sources are unchanged (210 MB of generated C in 200 files), but the
AArch64 toolchain behaves very differently from the desktop compiler:

- GCC 16 at `-O2` had not finished a 30 MB bank unit after **13.5 minutes** of
  CPU and about 3.5 GB resident, with four jobs threatening to exhaust 16 GB.
- At `-O1` the same class of unit (24.5 MB) compiles in **4m55s** and produces a
  55 MB object. Dispatch code is straight-line emulated instructions, so `-O1`
  gives up little.
- `build.sh` therefore compiles the four units above 12 MB strictly one at a
  time at `-O1`, then the remaining 145 small units in parallel at `-O2`, and
  keeps a fixed job cap.

The private rebuild was stopped deliberately at 17 of 149 bank translation
units to keep the machine usable for the next step; objects already built are
reused on resume.

### Still open

- The private 51-bank NRO is **not rebuilt or verified**. Whether static banks
  run correctly on AArch64 (live-byte validation, self-modifying-code fallback)
  is unknown; the desktop differential test covers the x86-64 runner only.
- No non-black DS frame has been confirmed in Eden. Title-screen rendering is
  the next checkpoint.
- Audio output, touch input and saving from the Switch UI remain unimplemented.


