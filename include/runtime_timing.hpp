// SPDX-License-Identifier: MIT
#pragma once
#include <cstdint>

namespace vore {
constexpr uint64_t arm9_clock = 67027964;
constexpr uint64_t frame_cycles = 2130ull * 263 * 2; // LCD lines in system cycles.
class FramePacer {
    uint64_t deadline_, period_, fraction_, remainder_ = 0;
public:
    FramePacer(uint64_t frequency, uint64_t now) : deadline_(now),
        period_(frequency * frame_cycles / arm9_clock),
        fraction_(frequency * frame_cycles % arm9_clock) {}
    uint64_t advance(uint64_t now) {
        deadline_ += period_;
        remainder_ += fraction_;
        if (remainder_ >= arm9_clock) { ++deadline_; remainder_ -= arm9_clock; }
        if (now > deadline_ && now - deadline_ > period_ * 4) {
            deadline_ = now; remainder_ = 0; // No runaway catch-up after stalls.
        }
        return now < deadline_ ? deadline_ - now : 0;
    }
    uint64_t deadline() const { return deadline_; }
};
} // namespace vore
