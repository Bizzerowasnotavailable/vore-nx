// SPDX-License-Identifier: MIT
// switch_host_info.cpp -- host description for the Switch runtime.
//
// The desktop runner collects CPU/OS/GPU details for triaging performance
// reports. On a console the hardware is known at build time, so the same
// snapshot is simply filled in.

#include <string>

#include "host_info.h"

namespace {

NdsHostInfo make_info() {
    NdsHostInfo info;
    info.cpu_brand = "Arm Cortex-A57 (4 cores)";
    info.cpu_vendor = "NVIDIA";
    info.cpu_cores_physical = 4;
    info.cpu_cores_logical = 4;
    info.ram_bytes = 3ull * 1024ull * 1024ull * 1024ull;
    info.os_name = "Nintendo Switch (Horizon)";
    info.os_version = "libnx";
    info.arch = "aarch64";
    return info;
}

}  // namespace

const NdsHostInfo& nds_host_info() {
    static const NdsHostInfo info = make_info();
    return info;
}

std::string nds_host_gpu_renderer_string() { return "software (GPU3D_Soft)"; }
