#include "runtime_video.hpp"

#include <cstdlib>
#include <iostream>
#include <vector>

static void check(bool ok) {
    if (!ok) {
        std::cerr << "runtime video check failed\n";
        std::exit(1);
    }
}

int main() {
    using namespace vore::video;
    check(rgba(0xFFFF0000u) == 0xFF0000FFu);
    check(rgba(0xFF00FF00u) == 0xFF00FF00u);
    check(rgba(0xFF0000FFu) == 0xFFFF0000u);
    check(rgba(0) == 0xFF000000u);
    std::vector<uint32_t> top(ds_width * ds_height, 0xFFFF0000u);
    std::vector<uint32_t> bottom(ds_width * ds_height, 0xFF0000FFu);
    for (const auto width : {256, 640, 1280, 1920}) {
        for (const auto height : {384, 720, 1080}) {
            const auto l = stacked_layout(width, height);
            check(l.x >= 0 && l.top_y >= 0);
            check(l.x + l.width <= width);
            check(l.bottom_y + l.height <= height);
            const auto first = bottom_touch(l, l.x, l.bottom_y);
            check(first.down && first.x == 0 && first.y == 0);
            const auto center = bottom_touch(l, l.x + l.width / 2,
                                             l.bottom_y + l.height / 2);
            check(center.down && center.x == 128 && center.y == 96);
            check(!bottom_touch(l, l.x - 1, l.bottom_y).down);
            check(!bottom_touch(l, l.x, l.bottom_y - 1).down);
            check(!bottom_touch(l, l.x + l.width, l.bottom_y).down);
            check(!bottom_touch(l, l.x, l.bottom_y + l.height).down);
            check(!bottom_touch(l, l.x, l.top_y).down);
            // Nontrivial padding and guards catch byte/pixel stride confusion.
            const std::size_t stride = width + 17;
            constexpr uint32_t guard = 0x12345678u;
            std::vector<uint32_t> fb(stride * height + 2, guard);
            check(draw(fb.data() + 1, stride * 4, width, height,
                       top.data(), bottom.data()));
            check(fb.front() == guard && fb.back() == guard);
            for (int y = 0; y < height; ++y) {
                for (int x = 0; x < width; ++x) {
                    const bool in_x = x >= l.x && x < l.x + l.width;
                    uint32_t want = 0xFF000000u;
                    if (in_x && y >= l.top_y && y < l.top_y + l.height)
                        want = rgba(top[0]);
                    if (in_x && y >= l.bottom_y && y < l.bottom_y + l.height)
                        want = rgba(bottom[0]);
                    check(fb[1 + y * stride + x] == want);
                }
                for (std::size_t x = width; x < stride; ++x)
                    check(fb[1 + y * stride + x] == guard);
            }
        }
    }
    uint32_t pixel = 0;
    check(!draw(nullptr, 5120, 1280, 720, nullptr, nullptr));
    check(!draw(&pixel, 4, 1280, 720, nullptr, nullptr));
    check(!draw(&pixel, 5, 1, 20, nullptr, nullptr));
    check(!draw(&pixel, 4, 1, 1, nullptr, nullptr));
    std::cout << "Runtime video: colours, bounds, byte stride, padding and touch mapping passed\n";
}
