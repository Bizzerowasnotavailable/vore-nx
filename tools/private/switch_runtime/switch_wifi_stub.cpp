// SPDX-License-Identifier: MIT
// switch_wifi_stub.cpp -- Wi-Fi MMIO aperture for the Switch port.
//
// The desktop runner implements this aperture with the vendored melonDS Wifi
// device model plus a full network stack. Bowser's Inside Story needs none of
// that to boot or play single-player, so the Switch build keeps the same
// memory-map contract and register-file behaviour but never emulates packets.
// Reads of the aperture always succeed (the DS firmware probes it during
// boot), writes are stored, and no events are ever scheduled.

#include <cstdint>
#include <cstring>

#include "wifi.h"

namespace {

// 0x04800000-0x0480FFFF is the ARM7-visible Wi-Fi aperture.
constexpr uint32_t kBase = 0x04800000u;
constexpr uint32_t kSize = 0x00010000u;

// Enough storage for every register the firmware touches. Registers are
// halfword-indexed in hardware; keep a flat byte image for simplicity.
uint8_t g_regs[kSize];

uint32_t offset_of(uint32_t addr) {
    return (addr - kBase) & (kSize - 1u);
}

}  // namespace

void nds_wifi_reset() { std::memset(g_regs, 0, sizeof(g_regs)); }

void nds_wifi_load_firmware(const uint8_t* data, uint32_t size) {
    (void)data;
    (void)size;
}

void nds_wifi_rebind_firmware(const uint8_t* data, uint32_t size) {
    (void)data;
    (void)size;
}

void nds_wifi_set_power_control(bool enabled, uint64_t timestamp) {
    (void)enabled;
    (void)timestamp;
}

uint64_t nds_wifi_next_event_time() { return UINT64_MAX; }

void nds_wifi_run_events(uint64_t timestamp) { (void)timestamp; }

uint16_t nds_wifi_debug_if() { return 0; }

uint16_t nds_wifi_debug_ie() { return 0; }

bool nds_wifi_address(int cpu, uint32_t addr) {
    if (cpu != 7) return false;
    return addr >= kBase && addr < kBase + kSize;
}

uint32_t nds_wifi_read(uint32_t addr, uint32_t width, bool powered) {
    if (!powered) return 0;
    uint32_t off = offset_of(addr);
    uint32_t value = 0;
    switch (width) {
        case 1:
            value = g_regs[off];
            break;
        case 2:
            std::memcpy(&value, &g_regs[off & ~1u], 2);
            break;
        default:
            std::memcpy(&value, &g_regs[off & ~3u], 4);
            break;
    }
    return value;
}

void nds_wifi_write(uint32_t addr, uint32_t value, uint32_t width, bool powered) {
    if (!powered) return;
    uint32_t off = offset_of(addr);
    switch (width) {
        case 1:
            // Byte writes are ignored by the real device.
            return;
        case 2:
            std::memcpy(&g_regs[off & ~1u], &value, 2);
            return;
        default:
            std::memcpy(&g_regs[off & ~3u], &value, 4);
            return;
    }
}
