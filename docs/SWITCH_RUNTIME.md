# Experimental local Switch runtime

This is separate from the published v0.1.1 installer. The original frontend
sources are in `tools/private/switch_runtime/`; hardware/CPU implementation comes
from a separately obtained ndsrecomp 0.6.10 checkout. No ROM-derived banks,
captures, saves, firmware or binary output are included in this repository.

## Build prerequisites

- devkitPro devkitA64, libnx, `nacptool` and `elf2nro`.
- Local ndsrecomp 0.6.10 source, including its matching arm-recomp-core submodule
  and vendored melonDS/FreeBIOS sources (see `docs/AOT.md` for pins).
- A local directory of generated `freebios_arm9.c`, `freebios_arm9_dispatch.c`,
  `freebios_arm7.c`, `freebios_arm7_dispatch.c` and their generated headers.
  Follow upstream's FreeBIOS bank-generation recipe: immutable BIOS banks must
  **not** use `--validate-live-bytes`.
- For a static-title build only: your privately generated cartridge bank set.
  Every cartridge/overlay/runtime-page bank must use live-byte validation.

The build does not download anything or obtain console keys/retail BIOS dumps.
The local runner used for testing also has the Horizon save-rename fix described
in `JOURNEY.MD`; an unpatched upstream checkout can repeatedly fail save flushes
when the destination already exists. A portable source patch is still pending.

```powershell
python tools/private/build_switch_runtime.py --nds /path/to/ndsrecomp-0.6.10 --bios-banks /path/to/generated-freebios --devkitpro C:/devkitPro --jobs 2
```

Default output is ignored `private/switch-runtime/vore-nx-interpreter.nro`.
Add `--banks /path/to/private-title-banks` for `vore-nx-private.nro`.
**That second NRO contains ROM-derived code and must not be redistributed.**
Neither build is an approved public release. Dependency licensing (including
GPL software rendering) and binary privacy review are separate release gates.

Large generated C units (at least 12 MB) compile serially at `-O1`; others use
`-O2` with bounded parallelism. Cached objects are keyed by source, header content
and compile command. Failed/interrupted compilation never replaces a cached
object. Linking uses an explicit list, not a wildcard that might pick up old
banks. Compiler logs are private files next to the objects.

## Run

Place your own exact European revision-0 `CLJP` image at
`sdmc:/switch/vore-nx/rom.nds`. The runtime checks size, game code and SHA-1 before
cartridge initialization. The published installer additionally checks SHA-256.
Use a separate test SD directory and back up existing saves before experimenting.

- A/B/X/Y, D-pad, L/R map to the corresponding DS controls.
- Plus is DS Start; Minus is DS Select.
- Both stick-clicks together exit and request save flush.
- ZR swaps screens; hold ZL for generated microphone blowing noise. All mappings
  can be changed in `runtime.ini`; see [runtime configuration](RUNTIME_CONFIG.md).
- Handheld touch is mapped only inside the displayed bottom LCD. The coordinate
  mapping is host-tested; actual Switch touch delivery is not yet validated.
- Sound is drained but not played; physical microphone capture and Wi-Fi are not implemented.

`sdmc:/switch/vore-nx/vore.log` records boot milestones, input transitions, actual
CPU cycle counts, vblank count, PCs and framebuffer colour statistics. A queued
buffer alone is not proof of visible rendering; use an Eden/real-device visual
check as well. A scheduler return below its requested target is logged as fatal
rather than counted as a successful guest frame.

Both screens fit completely side-by-side in 1280x720 (about 633x475 each,
12-pixel gap); vertical and experimental widescreen modes are configurable. Source
pixels are XRGB words; the presenter converts to RGBA bytes and honours libnx's
**byte** row stride. See the ROM-free `runtime-video` CTest target, also executed
by `python tools/build_host.py host`.
