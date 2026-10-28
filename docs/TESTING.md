# Testing boundaries

## ROM-free automated tests

```sh
cmake -S . -B build-host -DCMAKE_BUILD_TYPE=Release
cmake --build build-host --parallel
ctest --test-dir build-host --output-on-failure
python -m unittest discover -s tests -p "test_*.py"
```

These use synthetic data only. They do not need Nintendo files or credentials.
`vore-local-tests` is deliberately **not** registered with CTest. Python AOT
tests do not implicitly download dependencies; optional decompressor checks may
be skipped until the explicit private tool bootstrap has been run.

## Private-ROM integration

After building desktop tools, create a **new, empty** directory under `private/`:

```sh
cmake -E make_directory private/integration-check
build-host/vore-local-tests /path/to/your/rom.nds private/integration-check
python tools/verify_install.py --rom /path/to/your/rom.nds --install private/integration-check/4d8a3ffa13ad525db85e596d576675860a816aa77560ca87c4505451c172c60b
```

Adjust executable paths for Windows (`.exe`, possibly `Release/`). The C++ test
checks cancel rollback and preservation of pre-existing files before installing.
The independent Python verifier re-hashes the original ROM, derives the canonical
segment inventory from it, and compares every segment's metadata, bytes and
manifest digest. It rejects traversal names, duplicates and symlink payloads.
The extracted data is retained privately, not deleted after testing.

## Switch UI acceptance checklist — not yet verified

Use a homebrew-capable Switch and the public, asset-free NRO. No ROM is required
for the initial missing-file case.

- [ ] NRO boots and clearly displays **NOT PLAYABLE**.
- [ ] A with no ROM reports an error and remains usable.
- [ ] Invalid/unsupported ROM is rejected without extracting cartridge bytes.
- [ ] A verifies the exact supported ROM; progress remains responsive.
- [ ] X extracts all 237 segments; independent verification succeeds afterward.
- [ ] B cancels verification/extraction; no committed install is created.
- [ ] Existing install and unrelated user files survive a repeated X operation.
- [ ] + exits cleanly; Home/suspend/exit requests during work do not corrupt a
  committed installation.
- [ ] Disk-full/removed-SD behavior is checked on expendable test storage.

Power loss can leave a `.partial` directory. The installer intentionally does
not recursively delete unknown data. Move that directory aside before retrying.
Rename-based commit is not a power-loss/fsync guarantee.

## Eden

The first test used the supplied Windows `de7e6e01d4` CLI in a fresh portable
`user/` directory, without copying user keys or firmware. Its log recognized the
homebrew NRO but reported a failed 4 GiB backing allocation and then crashed.
See `JOURNEY.MD`; no rendered UI or gameplay was verified.

For a retest, make sufficient virtual commit available and use an isolated
portable test instance. Do not copy private keys, logs, configs or emulator user
directories into the source repository or release. A running process, successful
NRO load log, static-bank generation, or successful AArch64 object compilation
is **not** proof of correct rendered output or playable game behavior.

## Game acceptance — all pending

Before changing README playability status, retain dated evidence for title
screen, new game, Mario/Luigi exploration and combat, Bowser exploration and
combat, giant battles, touch/microphone interactions, sound, save/reload and a
complete playthrough. State the exact ROM revision, platform, build and known
failures. Never infer completion percentage from translated function counts.
