// SPDX-License-Identifier: MIT
// nds_host_shims.cpp -- host-environment adapters the portable runtime expects.
//
// The desktop runner pulls these from Windows/POSIX-specific units (profiling
// DLLs, unwind tables, environment lookups). On the Switch there is no such
// host: the shims below keep the runtime's contracts intact while doing the
// minimum a console frontend needs.

#include <cstdlib>
#include <cstring>
#include <cstdio>
#include <filesystem>
#include <string>

#include "state.h"

// ---- live overlay ------------------------------------------------------
// The live-overlay pipeline recompiles hot guest pages on the host and loads
// them as a shared library. A console build has no such host toolchain, so the
// overlay stays permanently dormant; these are the three platform hooks it
// asks for.
const char* live_overlay_library_suffix() { return ".nro"; }

bool live_overlay_is_final_library_path(const std::filesystem::path& path) {
    (void)path;
    return false;
}

std::string live_overlay_bundled_tcc_command(
    const std::filesystem::path& exe_dir) {
    (void)exe_dir;
    return std::string();
}

// ---- diagnostics.cpp uses setenv/getenv for its opt-in switches -----------
extern "C" int setenv(const char* name, const char* value, int overwrite) {
    (void)name;
    (void)value;
    (void)overwrite;
    return 0;
}

extern "C" int unsetenv(const char* name) {
    (void)name;
    return 0;
}
