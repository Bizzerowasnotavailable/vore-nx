// SPDX-License-Identifier: MIT
#pragma once
#include "runtime_video.hpp"
#include <array>
#include <cstdint>
#include <sstream>
#include <string>

namespace vore {
// libnx Npad button bits; checked against libnx by the Switch frontend.
inline uint64_t button(const std::string& name) {
    constexpr const char* names[] = {"a", "b", "x", "y", "stick_l", "stick_r",
        "l", "r", "zl", "zr", "plus", "minus", "left", "up", "right", "down"};
    for (unsigned i = 0; i < 16; ++i) if (name == names[i]) return uint64_t{1} << i;
    return 0;
}
inline bool binding(const std::string& text, uint64_t& mask) {
    if (text == "none") { mask = 0; return true; }
    std::istringstream parts(text);
    std::string name;
    mask = 0;
    if (text.empty() || text.back() == '+') return false;
    while (std::getline(parts, name, '+')) {
        auto bit = button(name);
        if (!bit || (mask & bit)) return false;
        mask |= bit;
    }
    return mask != 0;
}
inline bool held(uint64_t buttons, uint64_t binding_mask) {
    return binding_mask != 0 && (buttons & binding_mask) == binding_mask;
}
struct RuntimeConfig {
    video::Options video;
    std::array<uint64_t, 12> keys{button("a"), button("b"), button("minus"),
        button("plus"), button("right"), button("left"), button("up"),
        button("down"), button("r"), button("l"), button("x"), button("y")};
    uint64_t swap = button("zr"), mic = button("zl");
    uint64_t exit = button("stick_l") | button("stick_r");
    bool pace = true;
    unsigned renderer_threads = 0;
    std::string save_file = "rom.sav";
};
inline std::string trim(const std::string& s) {
    const auto first = s.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) return {};
    return s.substr(first, s.find_last_not_of(" \t\r\n") - first + 1);
}
// Transactional: a malformed file never applies a partial remapping.
inline bool parse_config(std::istream& input, RuntimeConfig& config, std::string& error) {
    RuntimeConfig next = config;
    std::string line;
    unsigned lineno = 0;
    while (std::getline(input, line)) {
        ++lineno;
        const auto comment = line.find('#');
        line = trim(line.substr(0, comment));
        if (line.empty()) continue;
        const auto eq = line.find('=');
        const auto key = trim(line.substr(0, eq));
        const auto value = eq == std::string::npos ? std::string{} : trim(line.substr(eq + 1));
        bool ok = false;
        if (key == "layout") {
            ok = value == "horizontal" || value == "vertical";
            if (ok) next.video.orientation = value == "horizontal" ? video::Orientation::Horizontal : video::Orientation::Vertical;
        } else if (key == "aspect") {
            ok = value == "native" || value == "stretch" || value == "adaptive";
            if (ok) next.video.aspect = value == "native" ? video::Aspect::Native :
                value == "stretch" ? video::Aspect::Stretch : video::Aspect::Adaptive;
        } else if (key == "swapped" || key == "pace") {
            ok = value == "true" || value == "false";
            if (ok && key == "swapped") next.video.swapped = value == "true";
            if (ok && key == "pace") next.pace = value == "true";
        } else if (key == "renderer_threads") {
            ok = value == "0" || value == "1" || value == "2";
            if (ok) next.renderer_threads = static_cast<unsigned>(value[0] - '0');
        } else if (key == "save_file") {
            ok = value.size() > 4 && value.size() <= 120 && value.substr(value.size()-4) == ".sav" &&
                value.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-. ") == std::string::npos &&
                value.find("..") == std::string::npos;
            if (ok) next.save_file = value;
        } else {
            constexpr const char* names[] = {"a", "b", "select", "start", "right", "left", "up", "down", "r", "l", "x", "y"};
            for (unsigned i = 0; i < 12; ++i)
                if (key == std::string("key.") + names[i]) ok = binding(value, next.keys[i]);
            if (key == "hotkey.swap") ok = binding(value, next.swap);
            if (key == "hotkey.mic") ok = binding(value, next.mic);
            if (key == "hotkey.exit") ok = binding(value, next.exit);
        }
        if (!ok) { error = "invalid setting at line " + std::to_string(lineno) + ": " + key; return false; }
    }
    config = next;
    error.clear();
    return true;
}
inline uint32_t key_mask(const RuntimeConfig& config, uint64_t buttons) {
    uint32_t mask = 0xFFFu;
    for (unsigned i = 0; i < 12; ++i) if (held(buttons, config.keys[i])) mask &= ~(1u << i);
    return mask;
}
} // namespace vore
