#pragma once

#include <algorithm>
#include <cstddef>
#include <cstdint>

namespace vore::video {

constexpr int ds_width = 256;
constexpr int ds_height = 192;

// DS renderer: 0xFFRRGGBB. libnx RGBA_8888: R,G,B,A bytes.
constexpr uint32_t rgba(uint32_t rgb) {
    return 0xFF000000u | ((rgb & 0xFFu) << 16) | (rgb & 0xFF00u) |
           ((rgb >> 16) & 0xFFu);
}

struct Layout {
    int x, top_y, bottom_y, width, height;
};

struct Touch {
    uint16_t x = 0, y = 0;
    bool down = false;
};

inline Touch bottom_touch(const Layout& l, int x, int y) {
    if (l.width <= 0 || l.height <= 0 || x < l.x || x >= l.x + l.width ||
        y < l.bottom_y || y >= l.bottom_y + l.height)
        return {};
    return {static_cast<uint16_t>((x - l.x) * ds_width / l.width),
            static_cast<uint16_t>((y - l.bottom_y) * ds_height / l.height), true};
}

// Two native-aspect screens, at most 2x size, with neither LCD cropped.
inline Layout stacked_layout(int width, int height, int gap = 12) {
    if (width <= 0 || height <= gap) return {};
    int h = std::min(ds_height * 2, (height - gap) / 2);
    h = std::min(h, width * ds_height / ds_width);
    const int w = h * ds_width / ds_height;
    const int y = (height - 2 * h - gap) / 2;
    return {(width - w) / 2, y, y + h + gap, w, h};
}

// stride_bytes is the API's row stride, not a count of uint32_t pixels.
inline bool draw(uint32_t* dst, std::size_t stride_bytes, int width, int height,
                 const uint32_t* top, const uint32_t* bottom) {
    if (!dst || width <= 0 || height <= 12 ||
        stride_bytes % sizeof(uint32_t) != 0 ||
        stride_bytes / sizeof(uint32_t) < static_cast<std::size_t>(width))
        return false;
    const auto layout = stacked_layout(width, height);
    if (layout.width == 0 || layout.height == 0) return false;
    const auto stride = stride_bytes / sizeof(uint32_t);
    for (int y = 0; y < height; ++y)
        std::fill_n(dst + y * stride, width, 0xFF000000u);
    const uint32_t* screens[] = {top, bottom};
    const int origins[] = {layout.top_y, layout.bottom_y};
    for (int screen = 0; screen < 2; ++screen) {
        if (!screens[screen]) continue;
        for (int y = 0; y < layout.height; ++y) {
            const auto* src = screens[screen] +
                              (y * ds_height / layout.height) * ds_width;
            auto* row = dst + (origins[screen] + y) * stride + layout.x;
            for (int x = 0; x < layout.width; ++x)
                row[x] = rgba(src[x * ds_width / layout.width]);
        }
    }
    return true;
}

} // namespace vore::video
