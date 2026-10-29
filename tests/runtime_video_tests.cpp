#include "runtime_video.hpp"
#include "runtime_config.hpp"
#include "runtime_microphone.hpp"
#include "runtime_timing.hpp"
#include <cstdlib>
#include <iostream>
#include <vector>

static void check(bool ok) {
    if (!ok) { std::cerr << "runtime frontend check failed\n"; std::exit(1); }
}

int main() {
    using namespace vore::video;
    check(rgba(0xFFFF0000u) == 0xFF0000FFu);
    check(rgba(0xFF00FF00u) == 0xFF00FF00u);
    check(rgba(0xFF0000FFu) == 0xFFFF0000u);
    std::vector<uint32_t> top(ds_width * ds_height), bottom(top.size());
    for (std::size_t i = 0; i < top.size(); ++i) {
        top[i] = 0xFF000000u | static_cast<uint32_t>(i);
        bottom[i] = 0xFFFF0000u | static_cast<uint32_t>(i);
    }
    unsigned layouts = 0;
    for (int width : {256, 640, 1280, 1920}) for (int height : {384, 720, 1080})
    for (auto orientation : {Orientation::Horizontal, Orientation::Vertical})
    for (auto aspect : {Aspect::Native, Aspect::Stretch, Aspect::Adaptive})
    for (bool swap : {false, true}) {
        const Options options{orientation, aspect, swap};
        const auto layout = arrange(width, height, options);
        for (const auto& r : layout) {
            check(r.x >= 0 && r.y >= 0 && r.width > 0 && r.height > 0);
            check(r.x + r.width <= width && r.y + r.height <= height);
        }
        check(orientation == Orientation::Horizontal ?
              layout[0].x != layout[1].x : layout[0].y != layout[1].y);
        const auto& touch_rect = layout[1];
        const auto touch = bottom_touch(layout, touch_rect.x, touch_rect.y);
        check(touch.down && touch.x == 0 && touch.y == 0);
        check(!bottom_touch(layout, touch_rect.x-1, touch_rect.y).down);
        check(!bottom_touch(layout, touch_rect.x, touch_rect.y-1).down);
        check(!bottom_touch(layout, touch_rect.x + touch_rect.width, touch_rect.y).down);
        check(!bottom_touch(layout, layout[0].x, layout[0].y).down);
        const auto last = bottom_touch(layout, touch_rect.x + touch_rect.width-1,
                                       touch_rect.y + touch_rect.height-1);
        check(last.down && last.x < 256 && last.y < 192);
        const std::size_t stride = width + 17;
        constexpr uint32_t guard = 0x12345678u;
        std::vector<uint32_t> fb(stride * height + 2, guard);
        check(draw(fb.data()+1, stride*4, width, height, top.data(), bottom.data(), options));
        check(fb.front() == guard && fb.back() == guard);
        for (int y = 0; y < height; ++y) {
            for (int x = 0; x < width; ++x) {
                uint32_t want = 0xFF000000u;
                for (int screen = 0; screen < 2; ++screen) {
                    const auto& r = layout[screen];
                    if (x >= r.x && x < r.x+r.width && y >= r.y && y < r.y+r.height) {
                        const auto& src = screen == 0 ? top : bottom;
                        want = rgba(src[((y-r.y)*192/r.height)*256 + (x-r.x)*256/r.width]);
                    }
                }
                check(fb[1 + y*stride + x] == want);
            }
            for (std::size_t x = width; x < stride; ++x) check(fb[1+y*stride+x] == guard);
        }
        ++layouts;
    }
    // Enhanced 3D surface widths must not be treated as native 256-pixel rows.
    std::vector<uint32_t> wide(342 * 192, 0xFF00FF00u), output(1280*720);
    check(draw(output.data(), 5120, 1280, 720, wide.data(), bottom.data(),
               {Orientation::Horizontal, Aspect::Adaptive, true}, 342, 256));
    const auto adaptive = arrange(1280, 720, {Orientation::Horizontal, Aspect::Adaptive, true});
    check(!bottom_touch(adaptive, adaptive[1].x, adaptive[1].y, 342).down);
    const auto wide_center = bottom_touch(adaptive, adaptive[1].x + adaptive[1].width/2,
                                          adaptive[1].y + adaptive[1].height/2, 342);
    check(wide_center.down && wide_center.x >= 127 && wide_center.x <= 128);
    uint32_t pixel = 0;
    check(!draw(nullptr, 5120, 1280, 720, nullptr, nullptr));
    check(!draw(&pixel, 4, 1280, 720, nullptr, nullptr));
    check(!draw(&pixel, 5, 1, 20, nullptr, nullptr));

    vore::RuntimeConfig config;
    std::string error;
    std::istringstream valid("layout=horizontal\naspect=adaptive\nkey.a=b\nkey.b=a\n"
        "hotkey.swap=l+zr\nhotkey.mic=none\nsave_file=My Game.sav\npace=false\n");
    check(vore::parse_config(valid, config, error));
    check(config.video.orientation == Orientation::Horizontal && !config.pace);
    check(config.save_file == "My Game.sav");
    check(vore::key_mask(config, vore::button("b")) == 0xFFEu);
    check(vore::key_mask(config, 0) == 0xFFFu);
    check(vore::key_mask(config, vore::button("x")) == 0xBFFu);
    check(vore::key_mask(config, vore::button("y")) == 0x7FFu);
    check(!vore::held(vore::button("zr"), config.swap));
    check(vore::held(vore::button("zr") | vore::button("l"), config.swap));
    check(!vore::held(~uint64_t{0}, config.mic));
    for (const char* bad : {"hotkey.swap=a+", "key.a=invalid", "save_file=../rom.sav",
                           "pace=maybe", "aspect=magic", "key.a=a+a", "layout vertical"}) {
        const auto previous = config;
        std::istringstream input(std::string("key.a=x\n") + bad);
        check(!vore::parse_config(input, config, error));
        check(config.keys == previous.keys); // No partial updates.
    }
    vore::microphone::blowing = false;
    check(vore::microphone::sample() == 2048);
    vore::microphone::blowing = true;
    bool lower = false, upper = false;
    for (int i = 0; i < 1000; ++i) {
        const auto sample = vore::microphone::sample();
        check(sample < 4096);
        lower |= sample < 1500; upper |= sample > 2500;
    }
    check(lower && upper && vore::microphone::conversions == 1001);
    vore::FramePacer pacer(1000000000, 0);
    uint64_t now = 0;
    for (int i = 0; i < 600; ++i) {
        check(pacer.advance(now) > 0);
        now = pacer.deadline();
    }
    check(now == 600ull * 1000000000ull * vore::frame_cycles / vore::arm9_clock);
    check(pacer.advance(now + 1000000000) == 0);
    check(pacer.deadline() == now + 1000000000);
    check(vore::benchmark_key_mask(1320, false) == 0xFFFu);
    check(vore::benchmark_key_mask(1320, true) == 0xFF7u);
    check(vore::benchmark_key_mask(1332, true) == 0xFFFu);
    check(vore::benchmark_key_mask(1500, true) == 0xFFEu);
    check(vore::benchmark_key_mask(2700, true) == 0xFEFu);
    std::cout << "Runtime frontend: " << layouts << " layouts, swap-aware touch, pixel/stride guards, "
                 "remapping/config validation and microphone ADC passed\n";
}
