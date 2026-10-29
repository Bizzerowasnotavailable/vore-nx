# vore-nx

An early Nintendo Switch static-recompilation project for **Mario & Luigi:
Bowser's Inside Story (Nintendo DS)**.

**Status: Switch NRO = ROM preparation, NOT PLAYABLE on Switch.** The included
NRO verifies and extracts a user-supplied ROM. It does not yet execute either DS
CPU or boot the game. Separately, a **private, locally built desktop runner** has
booted this ROM to the title screen, save-file screen and Toad Town exploration
with scripted input; that runner and its generated banks are not part of any
release. This is not a completed port or an emulator disguised as one.

[Development downloads](https://github.com/Bizzerowasnotavailable/vore-nx/releases)
include the installer NRO and source package. Read the limitations before use.

## Playability

| Feature | Status |
|---|---|
| Asset-free Switch NRO | Cross-compiled with devkitA64/libnx |
| Exact-ROM verification and private extraction | Implemented; test results in `JOURNEY.MD` |
| Private static banks (desktop) | 51 content-validated banks generated from measured Tier-3 coverage: main ARM9/ARM7 images, 6 ARM9 overlays, 2 relocated ARM7 aliases, 41 runtime-materialized page banks (private build only) |
| Private desktop ndsrecomp runtime | Boots to title screen, save-file screen, Toad Town exploration and in-game dialogue; scripted Start/A/D-pad input moves Mario (private build only) |
| Static-code share at runtime | Desktop session: 92.5% of ARM9 dispatches and 100% of ARM7 dispatches resolve to recompiled code instead of the interpreter (private measurement) |
| Static-bank correctness | Differential test, banks vs. forced Tier-3 interpretation: 6/6 framebuffer checkpoints byte-identical (private measurement) |
| Interactive desktop frontend | `tools/private/play_tk.py` (private tooling; needs a local runner build) |
| Switch runtime (AArch64) | Boots the DS machine, verifies the ROM, draws both screens into the Switch framebuffer; interpreter-only build verified in Eden (first frame at 2.4 s, ~6 fps, frames advancing) |
| Switch game execution | Runtime runs and presents, but no non-black DS frame has been confirmed and the 51-bank private build is not yet verified |
| Mario/Luigi and Bowser combat | Not verified |
| Giant battles, touch/microphone | Not verified |
| Audio and save/load (Switch) | Save file is written via the runner path; audio and UI saving not implemented |
| Ending / full playthrough | Not tested |
| Real Switch / Eden gameplay validation | Eden load/present path verified for the interpreter build; gameplay not validated |

Only **European revision 0 (`CLJP`)** is currently accepted for extraction:

```text
Size:    134217728 bytes
SHA-256: 4d8a3ffa13ad525db85e596d576675860a816aa77560ca87c4505451c172c60b
```

Other regions/revisions, modified or trimmed images are not supported. No ROM,
BIOS, firmware, game assets, or ROM-derived generated code is included.

## Use the NRO

1. Build below, or unpack the locally generated `dist/vore-nx-0.1.1.zip`.
2. Copy `vore-nx.nro` to your homebrew-capable Switch at
   `sdmc:/switch/vore-nx/vore-nx.nro`.
3. Place your own matching cartridge dump at `sdmc:/switch/vore-nx/rom.nds`.
4. Launch the NRO. **A** verifies; **X** verifies and extracts; **B** cancels
   while working; **+** exits. Allow at least 256 MiB free space for preparation.

Extracted files are private, under `sdmc:/switch/vore-nx/data/<sha256>/`.
Installation does not edit the ROM or overwrite an existing installation. Keep
the original ROM: extraction does not preserve every card sector. A cancelled
operation cleans up its own newly created files; after a power loss, move an
orphaned `.partial` directory aside before retrying.

**There is no "play" option yet.** The private desktop runtime observed during
development is not shipped and cannot be built from this repository alone: it
needs a locally built ndsrecomp runner plus private banks generated from your own
ROM. Do not redistribute your extracted files or translated banks. Owning a
cartridge and keeping assets external is not a universal legal guarantee; follow
the laws applicable to you. No encryption keys, download instructions, or
Nintendo security bypasses are provided.

## Build

### Switch (devkitPro)

In the devkitPro MSYS2 shell, with `switch-dev`/libnx installed:

```sh
make -j4
```

Or from Windows PowerShell (also handles Python not being on the MSYS PATH):

```powershell
python tools/build_switch.py
```

Output: `vore-nx.nro`. No ROM or ndsrecomp installation is needed to build this
asset-free installer. No game icon or ROMFS is embedded.

### Desktop tool and tests (C++17)

```sh
cmake -S . -B build-host -DCMAKE_BUILD_TYPE=Release
cmake --build build-host --parallel
ctest --test-dir build-host --output-on-failure
python -m unittest discover -s tests -p "test_*.py"
```

Use `build-host/vore-rom` (on Windows, possibly `build-host/Release/vore-rom.exe`)
to inspect or extract locally:

```sh
mkdir -p private/extracted
build-host/vore-rom inspect /path/to/your/rom.nds
build-host/vore-rom install /path/to/your/rom.nds private/extracted
```

Use `tools/verify_install.py` to independently check an installation against the
original ROM. Optional private integration tests and the pending Switch/UI/game
acceptance checklists are in [`docs/TESTING.md`](docs/TESTING.md).

`private/`, ROMs, generated banks, saves, and build intermediates are Git-ignored.
Never force-add them. A valid but unrecognized ROM can be inspected, with exit
code 3; installation requires the exact supported identity.

On Windows without a host compiler, the optional pinned portable toolchain is
available through `python tools/bootstrap_host.py host` (explicit downloads),
then `python tools/build_host.py host`.

### Private static recompilation

See [`docs/AOT.md`](docs/AOT.md) for the pinned, tested `prepare`, `audit`,
`generate`, and AArch64 object-smoke workflow. ARM9 analysis is decompressed
locally; overlays are metadata-only. Generated banks contain ROM-derived code
and must not be published or linked into the public installer NRO. Neither bank
emission nor object compilation establishes game execution or completeness.

### Package only distributable material

```sh
python tools/package_release.py --check
python tools/audit_public.py
python tools/package_release.py
```

The ZIP includes the NRO, checksums and an explicit source allowlist. The
packager rejects an unexpected icon/ROMFS/trailing payload and common embedded
personal-path/key markers. These checks complement source review; they are not
a proof of copyright clearance. ZIPs are never made from the entire workspace.

## Development

- [`JOURNEY.MD`](JOURNEY.MD): measured progress, toolchain results, blockers.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md): private data format and the
  remaining static recompilation/runtime work.
- [`docs/AOT.md`](docs/AOT.md): reproducible private static-bank preparation.
- Intended recompiler: [ndsrecomp](https://github.com/mstan/ndsrecomp) v0.6.10.
  No upstream runtime or generated game code is linked into this milestone.

Original project code is MIT-licensed; devkitPro/libnx and any future dependencies
retain their own licenses. Unaffiliated with Nintendo or the original developers.
