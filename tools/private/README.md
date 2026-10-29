# Private desktop pipeline tools

These scripts drive a **locally built** ndsrecomp runner against **your own**
cartridge dump. They exist so the static-code pipeline is reproducible instead
of being undocumented shell history. They are not part of the shipped NRO and
nothing they produce may be committed, attached to a release, or redistributed.

Everything here is deliberately free of cartridge content: the scripts contain
no ROM bytes, no game assets, no keys and no personal paths. All ROM-derived
output lands in a working directory you choose.

## What is private

`VORE_WORK` points at a working tree that holds, at minimum:

```text
<work>/runner-build/nds_runner.exe        built ndsrecomp runner
<work>/recompiler-build-direct/nds_recompile.exe
<work>/generated-bios/                    FreeBIOS + BIOS banks
<work>/banks*/                            generated static banks (ROM-derived)
<work>/analysis-images/                   decompressed images + overlays
<work>/coverage/                          manifests, seeds, runtime banks
```

Every one of those files is derived from the cartridge and is ignored by
`.gitignore` (`/private/`, `*.bin`, `*.log`, …). Treat the whole tree as
private.

## Environment

| Variable | Meaning |
|---|---|
| `VORE_WORK` | private working directory described above |
| `VORE_ROM` | your `rom.nds` (defaults to the parent of `VORE_WORK`) |
| `VORE_RUNNER` | runner executable path (defaults under `VORE_WORK`) |
| `VORE_AOT` | AOT preparation output (defaults to `../private/aot/<sha256>`) |
| `VORE_BANKS` | bank directory the runner build compiles in |

## Stages

1. **`prepare_overlays.py`** — decompress all ARM9 overlays from the cartridge
   and write the image set (`arm9.bin`, `arm7.bin`, `overlays/`, `overlays.json`)
   that the coverage ingest tool expects. Verifies each overlay against its
   declared size.

2. **`collect_coverage.py`** — boot the runner headless, drive a scripted input
   timeline into gameplay, and ask the runner for a Tier-3 coverage manifest
   (`coverage_manifest` on the debug server). The manifest records the guest's
   own executed code pages. Private evidence.

3. **`ndsrecomp/tools/ingest_coverage_manifests.py`** (upstream, not here) —
   resolve those pages back to ROM images, report *load-base* findings (code the
   game copied to an address no bank declares), and emit per-module entry-point
   seeds plus runtime-materialised page banks.

4. **`build_banks.py`** — turn those seeds into content-validated static banks:
   main images re-seeded from coverage, overlays compiled at their own load
   address, relocated ARM7 aliases, and the runtime page banks. Every bank is
   emitted with `--validate-live-bytes`, so a bank only runs where the guest's
   live bytes still match the image it was generated from.

5. **Runner build** — the runner CMake globs a bank directory, infers CPU from
   the `_arm9_`/`_arm7_` name segment, and registers each bank group behind an
   exact ROM SHA-1 match.

6. **`measure_play.py`** — one repeatable number set: boot throughput, Tier-3
   interpreter entries/instructions before and after a fixed play script, and
   interactive frames per second with per-frame framebuffer readback.

7. **`play_tk.py`** — interactive Tk window for real play: arrows, Z/X as A/B,
   Enter as Start, mouse as stylus.

`bench_fps.py` and `serve_capture.py` are the smaller pieces those scripts share
(server client, PNG writer, throughput probe).

## Honest limits

- Tier-1 (recompiled) code runs only where a bank exists *and* the live bytes
  still match. Everything else falls through to ndsrecomp's Tier-3 interpreter,
  which is correct but slow.
- Coverage is bounded by what the recorded session actually reached. Areas,
  menus, battles and minigames nobody played are not covered.
- None of this constitutes a playable Switch port. The desktop runner is a
  development instrument; the published NRO remains installer-only.
