# v0.1.1 — Host portability fix (NOT PLAYABLE)

This supersedes the first v0.1.0 development prerelease. It fixes a Linux GCC
`-Werror=ignored-attributes` failure by using a named RAII file deleter instead
of an attributed libc function-pointer type. No warnings are suppressed.

**This is still not a playable Switch port.** The public NRO only validates and
extracts a matching user-supplied European revision-0 `CLJP` ROM. It contains no
Nintendo game code/assets, BIOS, firmware, game icon, ROMFS or translated banks.
DS execution, rendering, audio, saves and gameplay are not integrated.

Included: installer NRO, allowlisted source ZIP (including that NRO), and SHA-256
checksums. Required open-source notices are in `source/docs/` inside the ZIP and
in the repository's `docs/THIRD_PARTY_NOTICES.md`.

Place your own `rom.nds` beside the NRO under `sdmc:/switch/vore-nx/`.
**A** verifies, **X** extracts, **B** cancels active work, **+** exits.
Keep the original ROM and all extracted/generated material private.

Windows-host tests, the Switch cross-build, and independent Linux CI
([run 40711337926](https://github.com/Bizzerowasnotavailable/vore-nx/actions/runs/40711337926))
pass; see `JOURNEY.MD` for exact results. Eden recognized the initial
NRO but failed its 4 GiB memory allocation and crashed; no rendered UI, physical
Switch operation or gameplay has been verified. Static-bank emission and
AArch64 object compilation are private development evidence, not playability.
