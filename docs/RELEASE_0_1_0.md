# v0.1.0 — ROM preparation (NOT PLAYABLE)

This is a development prerelease, **not a working Switch port** of Bowser's
Inside Story. It cannot boot the game. No DS execution backend is integrated.

## Included

- `vore-nx.nro`: original-code Switch ROM verifier/extractor, cross-built with
  devkitA64/libnx. No Nintendo game code/assets, BIOS, firmware, game icon or
  ROMFS is embedded.
- Source ZIP: original project source, build/test tools, documentation, required
  open-source notices, and the same NRO under `switch/vore-nx/`.
- Private, user-run AOT preparation tooling; generated cartridge banks are
  **not** included in this release or linked into the public NRO.

## Use

Place the NRO and your own exact European revision-0 `CLJP` dump in
`sdmc:/switch/vore-nx/`, naming the dump `rom.nds`. **A** verifies, **X** extracts,
**B** cancels active work, **+** exits. Extraction requires the exact SHA-256
listed in the README. Keep extracted data and generated banks private.

## Validation and limitations

Desktop synthetic tests, actual-ROM extraction tests and independent extracted
byte/hash comparison passed; measured details are in `JOURNEY.MD`.

The NRO cross-build passed. Eden recognized it but crashed after reporting a
failed 4 GiB backing-memory allocation. The rendered UI and on-device SD/input
paths have **not** been runtime-verified. No real Switch test or game progression
is claimed. Treat this as a developer milestone, not a compatibility release.

No ROM, extracted files, generated game code, emulator user data, personal paths,
credentials or security keys are part of the package. Open-source library
copyright notices are preserved; no legal guarantee is made for users' ROM use.
