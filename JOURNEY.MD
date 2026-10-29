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

## 2026-10-29 - Correct framebuffer setup: game visible in Eden

### Correction to the preceding presentation claim

Inspection found that `present()` constructed an **uninitialized local
`Framebuffer`** on every call, without `framebufferCreate()` or
`framebufferMakeLinear()`. It also treated `Framebuffer.stride` as pixels even
though the API supplies bytes, and the 2x stacked layout was 780 pixels tall
inside a 720-pixel output. A log line after `framebufferBegin()` did not establish
a valid queued buffer. The previous black-screen explanation (guest not writing
VRAM) was an assumption, not a demonstrated cause. The old FPS estimate is also
withdrawn: 600/37 is about 16, not 6, and those loop counts were not validated
against real CPU/vblank progress. The new evidence below supersedes that claim.

### Fix and independent tests

- Create one persistent 1280x720 RGBA8888 double buffer, enable linear access,
  render into the pointer actually returned by `framebufferBegin()`, use its
  byte stride, queue with `framebufferEnd()`, and close on exit.
- Both 256x192 LCDs now fit at 472x354 each, with a 12-pixel gap and no cropping.
  XRGB-to-RGBA conversion is retained.
- Original ROM-free `include/runtime_video.hpp` is shared with the frontend.
  Host tests check colour primaries, full visible output, bounds, padded byte
  strides, guard words and invalid inputs at twelve output-size combinations.
- Log actual CPU cycles, PCs, vblank count and nonblack/nonuniform pixel counts;
  reject a scheduler return below the requested target instead of silently
  incrementing a purported frame count.
- Enforce exact cartridge size and SHA-1 before device initialization (the
  earlier frontend checked only `CLJP`; its private registry alone checked SHA-1).
- Configure the controller explicitly. Start/Plus input was delivered through
  Eden's mapped keyboard and visibly changed the title to the file-selection UI.

### Measured visual result: interpreter-only, not a static-bank result

Eden's separate portable test instance visibly displayed the Nintendo/AlphaDream
startup sequence, the castle animation, full Mario & Luigi title with Start Game
and Mic Test, the save-file screen with two NEW FILE slots, then the opening
Toad Town scene after confirming New File / Start with A. This is an in-game
scene, not yet a verified Mario movement or combat test. The captures are
private local evidence, not committed artwork. The unrelated pre-existing Eden
process was left untouched.

```
[   3.038] video: created 1280x720 RGBA8888 linear double buffer
[   3.763] present: first buffer queued (1280x720 stride_bytes=5120)
[   3.765] progress frame=0 cyc9=1120639 cyc7=560324 vblank=0
[  52.432] progress frame=360 cyc9=404533248 cyc7=202266624 vblank=351
           nonblack=48942/48161 varied=1085/2308
```

Observed Eden status-bar samples were about **1-5 fps** during rendered scenes.
This is visibly functioning, slow execution, not a real-time playability claim.
The 51-bank build is still the performance/correctness checkpoint to complete.

### Source availability and remaining work

- Moved the original frontend/shims into public source under
  `tools/private/switch_runtime/`; generated registry/banks stay private.
- Added `tools/private/build_switch_runtime.py`: local dependency arguments,
  bounded jobs, serial giant banks, content-keyed object cache, atomic object
  replacement, failure propagation, and explicit object-list linking. See
  `docs/SWITCH_RUNTIME.md`. The native-Python build successfully cross-compiled
  an interpreter NRO, and an immediate second build reused all compiled objects
  (link/package only). A fresh Eden launch of that NRO rendered the castle
  animation, logged a first queued buffer at 2.872 s, and confirmed Start press
  and release (`0x3F7` then `0x3FF`). It exited the applet loop cleanly after
  1,111 iterations without a logged scheduler shortfall; the exit cause was not
  instrumented, so this does not validate the new exit chord.
- Added host-tested inverse bottom-LCD touch mapping and frontend touch polling,
  input-transition logging, and dual-stick-click exit/save flush. Actual touch
  delivery and these new controls still need runtime testing.
- Host validation so far: 260 parser/hash checks passed; video/touch-mapping
  tests passed; Python tests additionally cover object caching, header
  invalidation, failed-compile preservation and stale-object link exclusion.
  Final Python result: **35 passed, one platform skip**; synthetic tests also
  verify private-bank registry linking and serial `-O1` giant-bank selection.
  Public privacy audit passed for **56** source/license/workflow files.
- Still unverified: static banks on AArch64, real Switch hardware, combat,
  microphone, audio output, save/load round-trip and complete progression.

## 2026-10-29 - Requested runtime priorities: horizontal, saves and controls

User priorities: horizontal screens, regular framerate, standard SAVs,
widescreen, remappable controls, emulated microphone, screen-swap hotkey.

### Implemented and measured

- **Horizontal by default.** Original-aspect LCDs are side by side, with neither
  cropped. Vertical remains selectable in `runtime.ini`. A private Eden capture
  shows the castle/title on the left and reflected castle/menu on the right.
- **Swap hotkey.** ZR swaps display rectangles on press, not every held frame.
  Eden showed the menu on the left and title on the right after a logged swap.
  Touch tracks LCD identity, including swaps and adaptive viewport boundaries.
- **Remapping.** Original `runtime_config.hpp` parses transactional, validated
  INI settings for every DS button and the swap/microphone/exit actions. Bindings
  support single buttons, chords and `none`; this is file-based, not a GUI menu.
- **X/Y correctness fix.** The old frontend sent only `0x3FF` idle, but
  `nds_set_key_mask()` consumes bits 10/11 as X/Y. That held both buttons down
  permanently. Idle is now `0xFFF`; X and Y are mapped and tested independently.
- **Raw SAV loading fixed.** `nds_io_set_cartridge_save_path()` previously ran
  after `nds_io_load_cartridge()`, so existing saves were never loaded. It now
  runs before cartridge initialization, with explicit 8192-byte EEPROM config.
  Eden logged `save: loaded SRAM byte-identical to raw file` before boot.
  The supplied save is preserved as `.import-backup`; wrong sizes/unreadable
  saves fail closed. Default filename is `rom.sav`, configurable by basename;
  legacy `bis.sav` is retained only when no INI/default save exists.
- Cartridge metadata cross-check: upstream melonDS ROMList entry `0x504A4C43`
  (`CLJP`) uses save type 2, mapped by CartRetail to **8192 bytes**. No database
  or ROM payload was copied into this project.
- `tools/import_save.py` accepts exact raw SAVs and conservatively recognizes
  uniform padding/identical mirrored copies up to 512 KiB. It exclusively creates
  a new output; ambiguous trailers, emulator containers and overwrites are
  refused. This does not convert region/checksum formats or emulator savestates.

### AArch64 static-bank and performance checkpoint

- The earlier long-running Bash build eventually failed because its script was
  edited while Bash was still reading it. Completed giant-bank objects survived.
  Re-running the stable script finished all **149 bank translation units** and
  linked the **51-bank private NRO**. Do not edit an executing shell script again.
- Eden logged `private banks registered: yes`, advanced real CPU cycles/vblanks,
  and rendered non-black title/file-selection screens. No AArch64 differential
  framebuffer comparison is claimed; x86-64 parity is not proof of AArch64 parity.
- Single-threaded scene samples were around 9–11 guest fps. With the runtime's
  threaded software renderer enabled (`renderer_threads=2`), title samples were
  around **18 fps**, with later scenes around **10–12 fps**. These are different
  scene samples, not a controlled benchmark proving a particular speedup.
- One measured title interval: **18.26 guest fps**, **50.34 ms scheduler** and
  **4.39 ms presenter** per iteration. Later: 12.08 fps, 78.35 ms scheduler,
  4.37 ms presenter. CPU/device execution, not just screen copying, dominates.
- Counters confirm actual static execution: one title snapshot had ARM9
  10,957,007 static cache hits / 1,703,288 absent hits, ARM7 2,908,414 / 6, and
  cumulative Tier-3 instruction counts 1,405,761 / 10. These counters are not a
  complete coverage claim and do not establish game completion.
- Added monotonic, fractional-remainder pacing at the original LCD rate using
  **2130 system cycles × 263 lines × 2 = 1,120,380 ARM9 cycles/frame**. This
  corrects the earlier approximate 1,120,590 frontend budget. Long stalls reset
  the wall-clock deadline instead of causing runaway catch-up. A limiter cannot
  make a slow runtime full speed: **regular full-speed execution remains open**.

### Microphone and widescreen boundaries

- Hold ZL for deterministic generated blowing noise around the unsigned 12-bit
  microphone ADC midpoint; release supplies midpoint silence. The local Python
  builder stages the known channel-6 SPI extension in a private source copy and
  refuses unknown patch context. The local legacy checkout has the same guarded
  Switch-only extension so desktop builds do not require frontend headers.
- Eden logged microphone-button state changes. ADC generation and its channel
  patch are host-tested; **game Mic Test / giant-battle acceptance is unverified**.
  Ordinary title/gameplay samples did not request microphone conversions.
- `aspect=stretch` explicitly distorts LCDs to 16:9, without adding content.
  `aspect=adaptive` opts into a 342x192 3D surface and the upstream adaptive
  compositor. **BIS 2D camera expansion, HUD and object-culling patches are not
  implemented/validated; true game widescreen remains incomplete.** Do not
  advertise wide output rectangles as additional visible world content.

### Validation and build state

- Host: **260 parser/hash checks**, **144 display combinations** (orientations,
  aspects, swapped states, sizes), patterned pixel/stride/guard checks,
  swap-aware touch, controls/config, microphone samples and frame-pacer checks.
- Python: **40 passed, one platform skip**, including import preservation,
  invalid-size/container rejection and explicit/idempotent ADC patching.
- Final native-Python build cross-compiled the complete updated interpreter
  runtime, including staged microphone I/O and fractional-rate pacing. The
  private static-bank ELF/NRO also rebuilt successfully using retained bank
  objects. Public privacy audit passed for **64** source/license/workflow files.
- Private banks NRO remains private; no ROM, bank C/object, capture, log or save
  belongs in publication. New original source/config docs are public-safe.
- The running Eden instance holds the original NRO open, so the newest private
  ELF was packaged separately as `vore-nx-private-priorities.nro` rather than
  stopping that session to replace it. Final pacing/touch-boundary changes still
  need a fresh Eden launch after packaging. No release NRO was replaced.
