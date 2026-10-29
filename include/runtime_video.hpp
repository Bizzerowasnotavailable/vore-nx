// SPDX-License-Identifier: MIT
#pragma once
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>

namespace vore::video {
constexpr int ds_width = 256, ds_height = 192;
constexpr uint32_t rgba(uint32_t rgb) {
    return 0xFF000000u | ((rgb & 0xFFu) << 16) | (rgb & 0xFF00u) |
           ((rgb >> 16) & 0xFFu);
}
enum class Orientation { Horizontal, Vertical };
enum class Aspect { Native, Stretch, Adaptive };
struct Options {
    Orientation orientation = Orientation::Horizontal;
    Aspect aspect = Aspect::Native;
    bool swapped = false;
};
struct Rect { int x = 0, y = 0, width = 0, height = 0; };
using Layout = std::array<Rect, 2>; // Indexed by DS LCD, not display position.
struct Touch { uint16_t x = 0, y = 0; bool down = false; };

inline Layout arrange(int width, int height, Options options = {}, int gap = 12) {
    if (width <= gap || height <= gap || gap < 0) return {};
    const bool horizontal = options.orientation == Orientation::Horizontal;
    const int cell_w = horizontal ? (width - gap) / 2 : width;
    const int cell_h = horizontal ? height : (height - gap) / 2;
    const int aspect_w = options.aspect == Aspect::Native ? 4 : 16;
    const int aspect_h = options.aspect == Aspect::Native ? 3 : 9;
    const int h = std::min(cell_h, cell_w * aspect_h / aspect_w);
    const int w = h * aspect_w / aspect_h;
    if (w <= 0 || h <= 0) return {};
    Rect first{(width - (horizontal ? w * 2 + gap : w)) / 2,
               (height - (horizontal ? h : h * 2 + gap)) / 2, w, h};
    Rect second = first;
    if (horizontal) second.x += w + gap;
    else second.y += h + gap;
    return options.swapped ? Layout{second, first} : Layout{first, second};
}

inline Touch bottom_touch(const Layout& layout, int x, int y, int source_width = ds_width) {
    const Rect& r = layout[1];
    if (r.width <= 0 || r.height <= 0 || x < r.x || x >= r.x + r.width ||
        y < r.y || y >= r.y + r.height) return {};
    if (source_width < ds_width) return {};
    const int native_x = (x - r.x) * source_width / r.width - (source_width - ds_width) / 2;
    if (native_x < 0 || native_x >= ds_width) return {};
    return {static_cast<uint16_t>(native_x),
            static_cast<uint16_t>((y - r.y) * ds_height / r.height), true};
}

inline bool draw(uint32_t* dst, std::size_t stride_bytes, int width, int height,
                 const uint32_t* top, const uint32_t* bottom, Options options = {},
                 int top_width = ds_width, int bottom_width = ds_width) {
    if (!dst || width <= 12 || height <= 12 || top_width <= 0 || bottom_width <= 0 ||
        stride_bytes % sizeof(uint32_t) != 0 ||
        stride_bytes / sizeof(uint32_t) < static_cast<std::size_t>(width)) return false;
    const auto layout = arrange(width, height, options);
    if (layout[0].width == 0 || layout[0].height == 0) return false;
    const auto stride = stride_bytes / sizeof(uint32_t);
    for (int y = 0; y < height; ++y)
        std::fill_n(dst + y * stride, width, 0xFF000000u);
    const uint32_t* screens[] = {top, bottom};
    const int widths[] = {top_width, bottom_width};
    for (int screen = 0; screen < 2; ++screen) {
        if (!screens[screen]) continue;
        const auto& r = layout[screen];
        // Convert each source pixel once, then scale using a precomputed row.
        // Avoid a divide and channel shuffle for every enlarged output pixel.
        std::array<uint32_t, 4096> row{};
        if (r.width > static_cast<int>(row.size())) return false;
        int previous_y = -1;
        for (int y = 0; y < r.height; ++y) {
            const int sy = y * ds_height / r.height;
            if (sy != previous_y) {
                const auto* src = screens[screen] + sy * widths[screen];
                for (int x = 0; x < r.width; ++x)
                    row[x] = rgba(src[x * widths[screen] / r.width]);
                previous_y = sy;
            }
            std::copy_n(row.data(), r.width, dst + (r.y + y) * stride + r.x);
        }
    }
    return true;
}
} // namespace vore::video
