# Runtime controls, display and SAV files

These settings apply to the **experimental local runtime**, not the v0.1.1
installer. Place `runtime.ini` next to `rom.nds` on the test SD card:

```ini
# Defaults (file is optional). Settings are read at launch.
layout=horizontal
aspect=native
swapped=false
pace=true
renderer_threads=0
save_file=rom.sav

key.a=a
key.b=b
key.x=x
key.y=y
key.start=plus
key.select=minus
key.left=left
key.right=right
key.up=up
key.down=down
key.l=l
key.r=r
hotkey.swap=zr
hotkey.mic=zl
hotkey.exit=stick_l+stick_r
```

## Display and widescreen

- **Horizontal is the default**: top LCD on the left, touch LCD on the right.
  Both retain their native 4:3 aspect and fit completely inside a 16:9 output.
- `layout=vertical` restores stacking.
- **ZR swaps LCD positions once per press**, without changing the guest's screen
  routing. Touch follows the physical bottom DS LCD after a swap.
- `aspect=stretch` displays each LCD as 16:9. This distorts the original image;
  it does **not** reveal additional world content.
- `aspect=adaptive` requests the runtime's experimental 342x192 3D surface and
  adaptive 2D compositor. Native touch remains confined to its centered DS
  viewport. **BIS-specific 2D camera expansion, object culling and HUD behaviour
  have not been patched or validated. This is not a completed true-widescreen
  port.** Pure 2D scenes cannot gain new world content from a wider 3D renderer.

## Remapping and microphone

Every `key.*` and `hotkey.*` accepts one button name or a chord separated by `+`.
Available names: `a b x y l r zl zr plus minus left right up down stick_l stick_r`.
`none` disables an action. Example: `key.a=b`, `key.b=a`, `hotkey.swap=l+zr`.
Chords require all buttons held; the swap action triggers on the rising edge.
Avoid binding a hotkey to a gameplay button unless both actions are intended.
Invalid settings abort startup rather than partially applying a control map.
Remapping is file-based; no on-screen settings menu is implemented yet.

Hold **ZL** to emulate blowing. The microphone ADC channel receives generated
noise around its 12-bit midpoint; releasing it supplies silence. This is not
physical microphone capture and is not a voice-recognition implementation.
The patch is staged from local ndsrecomp sources during the Python build; the
dependency checkout is not edited by that builder. In-game Mic Test/giant-battle
acceptance remains a separate validation gate.

## Regular framerate

`pace=true` limits execution to the original approximately **59.826 DS frames/s**
using the DS cycle budget and a monotonic deadline. It never skips CPU work to
fake full speed. `pace=false` removes the limit for benchmarking. Slow hardware
still runs slowly: a limiter cannot turn a 10 fps execution path into 60 fps.
`renderer_threads=1` or `2` opts into threaded software rendering; `0` is the
conservative baseline. Performance and renderer correctness must be measured.
`vore.log` reports actual guest frame throughput, scheduler/presenter costs,
static dispatch hits, interpreter instructions and microphone conversions.

## Original cartridge / flashcart / emulator saves

The supported European revision-0 cartridge uses **8192-byte EEPROM saves**.
Reference metadata: melonDS `ROMList.cpp`, entry `0x504A4C43` (`CLJP`), save type
2; `NDSCart/CartRetail.cpp` maps type 2 to 8192 bytes. Only that cartridge identity
is supported. A SAV is the cartridge's separate battery memory, not a ROM edit.

1. Back up your save outside the test SD directory.
2. For a raw 8192-byte `.sav`, copy it as `rom.sav` next to `rom.nds`, or set
   `save_file=Your Game.sav` (basename only).
3. The runtime validates the size, preserves a `.import-backup`, sets the save
   path **before loading the cartridge**, and checks the resulting guest SRAM
   byte-for-byte against the input. Invalid sizes abort without replacing it.
4. Normal game save operations write raw `.sav` bytes, not an emulator container
   or savestate. Saving/loading actual game progress still needs round-trip tests.

For a flashcart's padded or mirrored image, convert into a **new** file:

```sh
python tools/import_save.py /path/to/original.sav /path/to/test-sd/switch/vore-nx/rom.sav
```

The importer accepts exact 8 KiB or larger multiples up to 512 KiB only when the
tail is all `00`, all `FF`, or identical mirrored copies. It rejects ambiguous
extra data and never overwrites either the original or an existing destination.
Export `.dsv` or other emulator containers as **raw SAV** first; emulator
savestates are not supported. No save checksum/region conversion is claimed.

Without an INI, an existing legacy `bis.sav` is used only if `rom.sav` is absent.
The current Horizon rename fallback is not power-loss-atomic. Preserve external
backups; the import backup is a recovery aid, not a guarantee against SD failure.
