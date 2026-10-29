// SPDX-License-Identifier: MIT
#pragma once
#include <cstdint>

namespace vore::microphone {
// Host-generated blowing noise, no captured/redistributed microphone audio.
// One ADC sample per guest microphone conversion, not per host frame.
inline bool blowing = false;
inline uint32_t noise = 0x12345678u;
inline uint64_t conversions = 0;
inline uint16_t sample() {
    ++conversions;
    if (!blowing) return 0x800u; // unsigned 12-bit ADC silence midpoint
    noise ^= noise << 13; noise ^= noise >> 17; noise ^= noise << 5;
    return static_cast<uint16_t>(0x800 + static_cast<int>(noise & 0x7FFu) - 1024);
}
} // namespace vore::microphone
