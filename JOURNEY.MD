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
- [ ] Future: Switch DS bus, CPU scheduler, IRQ/IPC, decompression/overlay banks,
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
