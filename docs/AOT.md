# Private ahead-of-time preparation (development only)

This pipeline prepares and translates the **main ARM9/ARM7 executable images**
from a user-supplied **European CLJP revision 0** cartridge. It is **not game execution, a playable port, a
complete static translation, or a replacement boot image**. It does not add a
runtime, link generated banks into the application, or translate overlays.

## Requirements and explicit bootstrap

Use Python **3.11 or newer** (the synthetic tests use `tomllib`). The provided
portable host build targets Windows x64. Other hosts can supply a compatible
`nds_recompile` executable with `--recompiler`.

Run from the repository root:

```powershell
python tools/bootstrap_host.py ndspy
```

This is an **explicit network command**, not an implicit part of preparation.
It downloads the pinned ndspy **4.2.0** pure-Python wheel into the workspace's
`local-work/downloads/`, verifies SHA-256, and leaves the complete wheel,
including its **GPL-3.0-or-later license**, intact. No pip/global installation
or third-party implementation is copied into this repository. ndspy is a
development dependency, not shipped in the application.

To acquire and build the optional portable host toolchain:

```powershell
python tools/bootstrap_host.py host
python tools/build_host.py recompiler
```

`bootstrap_host.py all` acquires both sets of dependencies. All download URLs
and SHA-256 pins are in that script; a private machine-readable record is
written under `local-work/`. Existing mismatched dependencies are rejected, not
silently overwritten. The matching source is a private download, not a change
to the supplied ndsrecomp tree.

Pinned development inputs:

| Dependency | Pin |
|---|---|
| ndsrecomp v0.6.10 | `aa40b575b6f68a537f24ff3e4c94b567baa25587` |
| ARM core (release's gitlink) | `705e71b8aff3ad64fe78f77c3c94bd93158554dd` |
| toml++ | 3.4.0, SHA-256 `6b5172ad4dd6519aec67b919181fa7a38a2234131e5b2afa232dfe444819783e` |
| Zig | 0.15.2 Windows x64 wheel, SHA-256 `ca80dc9c70dbdfdd9ee51d000de3501a95d33d9782ab9ab9b56f700484ebcd83` |
| ndspy | 4.2.0 wheel, SHA-256 `d3b03e57ef5ba450e766035e1908293f7a6ba1a738736fae42b2c66952abb85b` |

`build_host.py` uses Zig directly, avoiding MSYS/CMake response-file path issues.
Its C++20 source list matches the pinned upstream recompiler CMake target.
The output is `../local-work/recompiler-build-direct/nds_recompile.exe`.
`python tools/build_host.py host` also builds and runs the repository's C++17
host tests, placing those executables in ignored `build-host/`.

## Verify, prepare, audit, generate

Place your own cartridge at `../rom.nds`, or pass `--rom PATH`. Only original-DS
**European CLJP revision 0**, SHA-256
`4d8a3ffa13ad525db85e596d576675860a816aa77560ca87c4505451c172c60b`, is accepted.
CLJP is the European release; CLJJ identifies the Japanese release. This region
label does not change the exact hash/code/revision gate.

```powershell
python tools/aot.py prepare
python tools/aot.py audit
python tools/aot.py generate
```

Every command first reads an immutable snapshot and verifies its entire hash,
game code, revision, unit type, and header CRC **before creating outputs**.
There is no command-line hash bypass. `aot.py` never downloads anything.
`config` is an alias for `prepare`; configs are always derived from verified
prepared bytes, not independently hand-authored sizes/hashes.

The default output is `private/aot/<supported-cartridge-sha256>/`. `--out` may
select another directory **only below repo `private/` or workspace
`local-work/`**. Public paths, traversal outside those roots, and escaping
symlinks/junctions are rejected. Differing existing prepared inputs or generated
banks are not overwritten: choose another private output directory.

Outputs, all private:

- `inputs/arm9.raw.bin`, `arm7.raw.bin`: unchanged extracted main images.
- `inputs/arm9.bin`, `arm7.bin`: analysis images (expanded where demonstrated).
- Matching TOML configs: flat guest load address, actual file byte length, entry
  address/mode, actual prepared-file SHA-1, and proven SDK copy aliases.
- `manifest.json`: cartridge identity, recipe pins, image hashes, compression
  evidence, SDK metadata, and coverage qualifications.
- `overlays.json`: descriptors only, including FAT mapping, load/BSS ranges,
  initializer ranges and compression flags. No overlay payload extraction or
  guessed load-address entry seeds.
- `logs/`, `audit.json`, `generation.json`: tool results and output hashes.
- `generated/bis_arm9_main/` and `generated/bis_arm7_main/`: validated C banks.

Generation always uses `--shards 2 --validate-live-bytes` and the bank names
`bis_arm9_main` / `bis_arm7_main`. Files are emitted into a fresh private staging
directory first. Header, body shards, nonempty dispatch table, exact dispatch
row count, and live-byte validation records are checked before accepting them;
process exit zero alone is insufficient. This is still **static C output**, not
a runtime compiler.

## Compression policy

The pipeline checks SDK module parameters and a strict end-of-image executable
compression footer, including padding, compressed span and expansion size. It
does **not** use ordinary BIOS LZ10 decompression or guess at appended trailers.
The pinned ndspy executable-code decompressor is called only with corroborating
footer evidence and bounded output size. The result must have the predicted
length and preserve the exact uncompressed prefix; when SDK parameters exist,
they must remain unchanged and the expanded end must match the autoload-table
end. Validated autoload descriptors become readability aliases, **not guessed
entry points**.

Expanded analysis bytes are not patched: in particular, the SDK compressed-end
word is retained. **Do not install the expanded image as the runtime boot
image.** The original cartridge/startup must perform its own decompression and
copies. The recompiler's sandbox relocation scan is disabled for expanded
analysis input to avoid simulating decompression a second time; its SDK copy
aliases are declared explicitly instead. The scan remains enabled for the raw
ARM7 main image.

If compression evidence is uncertain, preparation refuses to imply success.
For an explicitly limited alternative, use a **different** output directory:

```powershell
python tools/aot.py generate --raw-startup-only --out private/aot-startup-only
```

This excludes the demonstrably compressed tail from discovery. If even the tail
boundary cannot be established, it bounds translation to one explicit startup
instruction. The manifest labels the limitation; the compressed body is **not**
claimed as translated. Absence of SDK/footer evidence on ARM7 is recorded as
such, not presented as a universal proof that every region is uncompressed.

## Optional AArch64 translation smoke check

After generation, supply your existing devkitA64 compiler explicitly:

```powershell
python tools/aot.py smoke --cc C:/devkitPro/devkitA64/bin/aarch64-none-elf-gcc.exe
```

Adjust the compiler's native path for your installation. An MSYS `/opt/devkitpro`
alias is not necessarily a valid path in Windows PowerShell.

This compiles every generated body and dispatch translation unit with
`-std=gnu11 -O0 -g0`, and `NDS_STATIC_CPU=0` for ARM9 or `1` for ARM7. Include
directories, relative to the matching private ndsrecomp source, are:

- `recompiler/armv4t` (`runtime_arm.h`)
- `external/arm-recomp-core/common` (**`runtime_arm_types.h`**)
- `external/arm-recomp-core/profiles/armv5te_nds`
- The generated bank's directory

Override that source with `--source PATH` if needed; both runtime ABI headers
must still match their pinned SHA-256 values. Objects and compile logs
remain under the selected private output. Each object must be a nonempty
ELF64 AArch64 relocatable. **This does not link or test the runtime, scheduler,
devices, audio, rendering, save handling, or game correctness.**

## Synthetic tests and remaining coverage gaps

```powershell
python -B -m unittest discover -s tests -p test_aot.py -v
```

Tests use only invented inputs and cover the exact-hash rejection gate,
no-write-on-rejection behavior, public output rejection, link escape (where
the host permits creating links), actual config identities, compression guards,
raw-startup limitations, dependency rejection and generated-file validation.
They never open the real cartridge.

All **141 ARM9 overlay descriptors** remain metadata-only. Main CFG discovery
can miss indirect callbacks, runtime entry points, copied-code variants and
other materialized code. Nonzero indirect unknown counts are retained in private
reports. Live-byte validation is required but does not itself prove completeness
or correctness. Runtime integration and title-specific coverage validation remain
separate work. Do not publish, package, commit or upload the cartridge, extracted
images, generated C, objects, private logs or private manifests.
