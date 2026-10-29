# Switch performance experiments

Full speed means approximately **59.826 guest frames/s**, not repeated host
presents or skipped CPU/device work. Real hardware remains untested; Eden
measurements also include translation of the generated AArch64 executable, and
that second emulation layer is currently the dominant cost (see below).
Compilation does not establish either correctness or speed.

## Repeatable measurements

The experimental runtime accepts these **opt-in test settings** in `runtime.ini`:

```ini
benchmark_frames=1200
benchmark_scenario=idle
pace=false
profile=true
renderer_threads=2
```

`benchmark_frames=0` (the default) is normal interactive play. Test mode disables
live game inputs and detaches cartridge save writes **after loading** the save;
it does not write scripted progress back to the imported SAV. The runtime logs
native LCD pixel hashes at fixed cycle targets and exits after the requested
number of guest frames. A private `benchmark.done` file signals completion.

`benchmark_scenario=town` adds fixed Start/A/D-pad input; use 3600 frames for
the longer sequence. Merely selecting the scenario does not prove that it
reaches a particular area. Check the captures/state and compare checkpoints.
No more than 3600 frames can be requested by the current bounded test mode.

Run variants with the same ROM, loaded SAV, generated-firmware identity,
renderer settings and scenario. Compare only completed runs:

```sh
python tools/private/compare_switch_bench.py private/reference.log private/candidate.log --min-frame 600
```

This refuses missing checkpoints, fatal/incomplete runs and mismatched targets.
It reports mismatched hashes and post-warm-up median guest throughput, scheduler
cost and presentation cost. Hash matching is useful regression evidence, not a
full byte-for-byte dump comparison or proof of all gameplay. Compare inputs and
all relevant states as well before claiming broader compatibility.

Keep compilation and other heavy work **out of measured intervals**. Preserve
original settings/saves and restore the INI after testing. Logs and generated
objects can contain local paths and ROM-derived information: never publish
those artifacts or screenshots through the source/release pipeline.

## Measured results (private builds)

Same ROM, same loaded (empty but valid) SAV, same generated firmware, two
renderer workers, no pacing, 1,200 idle frames, statistics over intervals
ending at frame 600 and later:

| Variant | Median guest fps | Median scheduler cost | LCD hashes |
|---|---:|---:|---|
| GCC banks, original runtime | 16.97 | 54.61 ms | reference |
| Switch hardware-counter profiling | 17.45 | 53.04 ms | 10/10 |
| GCC banks, `-O3`/LTO runtime | 19.58 | 46.82 ms | 10/10 |
| Clang `-O2` banks, ordinary runtime | 16.58 | 56.15 ms | 10/10 |
| Whole-program LTO, `-O3`, static CPU, minimal profiling | **21.46** | **42.37 ms** | **10/10** |

The same banks under the native x86-64 desktop runner sustain 161.7M ARM9
cycles/s while booting and 74.1 fps interactive with per-frame framebuffer
readback (124% of DS realtime). Eden sustains ~24M ARM9 cycles/s on the LTO
build, which is a 3.5x to 6.7x penalty for re-translating AArch64. Per-frame
logs put ARM9 + ARM7 execution at the overwhelming majority of the frame, with
all remaining buckets combined under a quarter. Reaching 60 fps in Eden would
therefore require dropping most guest work, which this project does not do;
real hardware is the next meaningful measurement.

## Build knobs

The local Python runtime builder now supports:

- Per-bank `NDS_STATIC_CPU=0` (ARM9) / `1` (ARM7), including FreeBIOS C units.
  This is the upstream per-source specialization: the shared scheduler still
  switches CPUs normally; only code that permanently belongs to one CPU is
  specialized. Unknown/ambiguous bank CPU names are refused.
- Switch system-counter profiling, with counter-frequency ns calibration,
  instead of the generic `std::chrono` timer path. Patched runtime headers and
  sources are staged privately so quoted includes select matching headers.
- `--optimization O3 --lto` for runtime optimization, without fast-math.
- `--runtime-only` to build the runtime/registry without recompiling banks.
- `--minimal-profiling` to omit fine-grained host timing scopes. Coarse frame
  timings, actual cycles, guest instruction/dispatch counters and rendering
  stay intact. The log explicitly labels fine-grained timing as unavailable;
  zero bucket totals must not be advertised as free guest execution.
- Experimental `--bank-lto --lto --banks ...` for a whole runtime/bank IR build.
  This is expensive (about 50 minutes and ~240 MB of IR objects for the current
  51-bank set) and the link treats LTO type mismatches as errors. Measured on
  the 1,200-frame timeline it takes the build from 19.58 to 21.46 median guest
  fps against the same reference run and hashes; it is still far from 60.

For experimental Clang bank objects, using a local pinned Zig driver and the
devkitA64 newlib headers:

```sh
python tools/private/build_switch_llvm_banks.py --nds /path/to/ndsrecomp --banks /path/to/private-banks --zig /path/to/zig --devkitpro /path/to/devkitpro --output private/llvm-banks --jobs 2
```

This uses `-O2` on all units, bounds parallelism, creates objects atomically,
records source/header/command keys and checks ELF64/AArch64 relocatable headers.
Metadata is private. Compiler choice can regress performance: smaller binaries
are not sufficient evidence of a faster executable.

An explicitly inventoried experimental link can combine those bank objects with
a separately built devkitA64 runtime:

```sh
python tools/private/link_switch_variant.py --core-objects private/runtime/obj-private --bank-objects private/llvm-banks --banks /path/to/private-banks --output private/variants --name vore-test --lto
```

Do not mix incompatible runtime ABI/header versions. The linker checks source
digests, bank header-key consistency, recorded CPU specialization and object
architecture; runtime AOT live-byte validation remains enabled. Runtime
compiler/header compatibility and checkpoint parity remain additional gates.

**Every NRO linked with cartridge banks contains ROM-derived code and must stay
private.** These tools are not a new public binary release. See `JOURNEY.MD`
for actual measurements, including experiments that did not help.
