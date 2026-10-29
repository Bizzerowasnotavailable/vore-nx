// SPDX-License-Identifier: MIT
// switch_main.cpp -- libnx frontend for the vore-nx static runtime.
//
// The platform layer loads the user's cartridge image, initializes the DS
// hardware runtime, and presents both LCDs. Static banks execute covered code;
// the Tier-3 interpreter executes any uncovered code.
//
// Everything game-specific lives in ROM-derived generated banks that are NOT
// part of the shipped NRO. The public build links only the BSD-licensed
// FreeBIOS banks and falls back to the Tier-3 interpreter for cartridge code.

#include <switch.h>

#include <cstdarg>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <sys/stat.h>
#include <string>
#include <vector>

#include "state.h"
#include "runtime_arm.h"
#include "scheduler.h"
#include "bus.h"
#include "io.h"
#include "spu.h"
#include "vram.h"
#include "gpu2d.h"
#include "gpu3d.h"
#include "direct_boot.h"
#include "generated_firmware.h"
#include "firmware_state.h"
#include "title_patches.h"
#include "live_overlay.h"
#include "emu_profile.h"
#include "pc_profile.h"
#include "dispatch_timing.h"
#include "coverage_manifest.h"
#include "title_banks.h"

#include "freebios_images.h"
#include "sha1.h"
#include "runtime_video.hpp"
#include "runtime_config.hpp"
#include "runtime_microphone.hpp"
#include "dispatch_stats.h"
#include "tier3.h"
#include "runtime_timing.hpp"

extern "C" {
extern const DispatchEntry g_dispatch_freebios_arm9[];
extern const unsigned g_dispatch_freebios_arm9_len;
extern const DispatchEntry g_dispatch_freebios_arm7[];
extern const unsigned g_dispatch_freebios_arm7_len;
}

namespace {

constexpr const char* kRoot = "sdmc:/switch/vore-nx";
constexpr const char* kRomPath = "sdmc:/switch/vore-nx/rom.nds";
constexpr const char* kConfigPath = "sdmc:/switch/vore-nx/runtime.ini";
constexpr const char* kMacPath = "sdmc:/switch/vore-nx/mac.bin";
constexpr const char* kFirmwarePath = "sdmc:/switch/vore-nx/firmware.bin";
constexpr const char* kLogPath = "sdmc:/switch/vore-nx/vore.log";

// ARM9 core clock 67.027964 MHz, 59.826 Hz refresh: one frame of DS time.
constexpr uint64_t kArm9CyclesPerFrame = vore::frame_cycles;
vore::RuntimeConfig g_config;
static_assert(HidNpadButton_ZR == (1ull << 9) && HidNpadButton_Down == (1ull << 15),
              "portable controller bits must match libnx");

// ---- diagnostics ---------------------------------------------------------
// Once the applet starts presenting there is no visible console, and Eden does
// not surface stdout. Milestones therefore go to a small file on the SD card so
// a boot that never reaches its first frame can be located precisely.
FILE* g_log = nullptr;
u64 g_log_tick0 = 0;

void vlog(const char* fmt, ...) {
    if (!g_log) return;
    const double seconds =
        static_cast<double>(armGetSystemTick() - g_log_tick0) /
        static_cast<double>(armGetSystemTickFreq());
    std::fprintf(g_log, "[%8.3f] ", seconds);
    va_list ap;
    va_start(ap, fmt);
    std::vfprintf(g_log, fmt, ap);
    va_end(ap);
    std::fputc('\n', g_log);
    std::fflush(g_log);
}

void log_open() {
    g_log = std::fopen(kLogPath, "wb");
    g_log_tick0 = armGetSystemTick();
    vlog("vore-nx runtime starting");
}


std::vector<uint8_t> read_whole_file(const char* path, std::string* error) {
    std::vector<uint8_t> out;
    FILE* f = std::fopen(path, "rb");
    if (!f) {
        if (error) *error = std::string("cannot open ") + path;
        return out;
    }
    if (std::fseek(f, 0, SEEK_END) != 0) {
        std::fclose(f);
        if (error) *error = std::string("cannot seek ") + path;
        return out;
    }
    long size = std::ftell(f);
    if (size <= 0) {
        std::fclose(f);
        if (error) *error = std::string("empty ") + path;
        return out;
    }
    std::rewind(f);
    out.resize(static_cast<size_t>(size));
    size_t got = std::fread(out.data(), 1, out.size(), f);
    std::fclose(f);
    if (got != out.size()) {
        if (error) *error = std::string("short read of ") + path;
        out.clear();
    }
    return out;
}

bool write_whole_file(const char* path, const void* data, size_t size) {
    FILE* f = std::fopen(path, "wb");
    if (!f) return false;
    bool ok = std::fwrite(data, 1, size, f) == size;
    std::fclose(f);
    return ok;
}

// Direct-boot machine: guest writes go through the device bus so the copied
// cartridge binaries acquire write provenance, exactly like the desktop runner.
struct SwitchDirectBootMachine final : NdsDirectBootMachine {
    void write16(int cpu, uint32_t addr, uint16_t value) override {
        bus_device_write16(cpu == 1 ? 7 : 9, addr, value);
    }
    void write32(int cpu, uint32_t addr, uint32_t value) override {
        bus_device_write32(cpu == 1 ? 7 : 9, addr, value);
    }
    void cp15_write(uint32_t crn, uint32_t crm, uint32_t op2,
                    uint32_t value) override {
        runtime_coproc_write(15, 0, crn, crm, op2, value);
    }
    void set_cpu_boot(int cpu, uint32_t entry, uint32_t sp, uint32_t sp_irq,
                      uint32_t sp_svc) override {
        scheduler_set_cpu_boot(cpu, entry, sp, sp_irq, sp_svc);
    }
    void set_wramcnt(uint8_t value) override { nds_io_set_wramcnt(value); }
    void set_arm7_bios_prot(uint32_t value) override {
        nds_io_set_arm7_bios_prot(value);
    }
    void set_post_boot_latches() override {
        nds_io_apply_direct_boot_latches();
    }
    void copy_logo_into_arm9_bios(const uint8_t* logo,
                                  uint32_t size) override {
        bus_patch_arm9_bios(0x20, logo, size);
    }
};

std::array<uint8_t, 6> load_or_create_mac() {
    std::array<uint8_t, 6> mac = {0x02, 0x00, 0x00, 0x00, 0x00, 0x01};
    std::string error;
    std::vector<uint8_t> stored = read_whole_file(kMacPath, &error);
    if (stored.size() == 6) {
        std::memcpy(mac.data(), stored.data(), 6);
        return mac;
    }
    // Per-install identity, never a shared constant.
    randomGet(mac.data() + 3, 3);
    mac[0] = 0x02;  // locally administered, unicast
    write_whole_file(kMacPath, mac.data(), mac.size());
    return mac;
}

struct RomInfo {
    bool ok = false;
    const char* error = "";
};

RomInfo check_rom(const std::vector<uint8_t>& rom) {
    RomInfo info;
    if (rom.size() != 134217728u) {
        info.error = "ROM size does not match the supported cartridge";
        return info;
    }
    if (std::memcmp(rom.data() + 0x0C, "CLJP", 4) != 0) {
        info.error =
            "unexpected game code (this build expects the European revision-0 "
            "cartridge, CLJP)";
        return info;
    }
    if (gba::sha1(rom.data(), rom.size()).hex() !=
        "5f35bfbf79a0947740795dd770d99e8eea3ac85e") {
        info.error = "ROM digest does not match European revision 0";
        return info;
    }
    info.ok = true;
    return info;
}

// ---- presentation -------------------------------------------------------
Framebuffer g_framebuffer{};
uint16_t g_presented_widths[2] = {256, 256};

bool video_init() {
    Result rc = framebufferCreate(&g_framebuffer, nwindowGetDefault(),
                                  1280, 720, PIXEL_FORMAT_RGBA_8888, 2);
    if (R_FAILED(rc)) {
        vlog("fatal: framebufferCreate rc=0x%08X", rc);
        return false;
    }
    rc = framebufferMakeLinear(&g_framebuffer);
    if (R_FAILED(rc)) {
        vlog("fatal: framebufferMakeLinear rc=0x%08X", rc);
        framebufferClose(&g_framebuffer);
        return false;
    }
    vlog("video: created 1280x720 RGBA8888 linear double buffer");
    return true;
}

void present() {
    static bool reported_failure = false;
    static bool reported_success = false;
    u32 stride_bytes = 0;
    auto* base = static_cast<uint32_t*>(
        framebufferBegin(&g_framebuffer, &stride_bytes));
    if (!base) {
        if (!reported_failure) {
            reported_failure = true;
            vlog("present: framebufferBegin failed");
        }
        return;
    }
    uint16_t widths[2] = {256, 256};
    const uint32_t* lcd[2];
    for (int i = 0; i < 2; ++i)
        lcd[i] = g_config.video.aspect == vore::video::Aspect::Adaptive ?
            nds_gpu2d_adaptive_framebuffer(i, &widths[i]) : nds_gpu2d_framebuffer(i);
    const bool drawn = vore::video::draw(base, stride_bytes, 1280, 720,
        lcd[0], lcd[1], g_config.video, widths[0], widths[1]);
    g_presented_widths[0] = widths[0]; g_presented_widths[1] = widths[1];
    framebufferEnd(&g_framebuffer);
    if (drawn && !reported_success) {
        reported_success = true;
        vlog("present: first buffer queued (1280x720 stride_bytes=%u)", stride_bytes);
    }
}

void log_progress(uint64_t frame) {
    uint32_t nonblack[2]{};
    uint32_t varied[2]{};
    for (int screen = 0; screen < 2; ++screen) {
        const uint32_t* pixels = nds_gpu2d_framebuffer(screen);
        if (!pixels) continue;
        for (int i = 0; i < 256 * 192; ++i) {
            nonblack[screen] += (pixels[i] & 0xFFFFFFu) != 0;
            varied[screen] += pixels[i] != pixels[0];
        }
    }
    vlog("progress frame=%llu cyc9=%llu cyc7=%llu vblank=%llu "
         "pc9=%08X pc7=%08X nonblack=%u/%u varied=%u/%u",
         (unsigned long long)frame,
         (unsigned long long)scheduler_cpu_cycles(0),
         (unsigned long long)scheduler_cpu_cycles(1),
         (unsigned long long)nds_event_counts().vblank9,
         scheduler_cpu_state(0).R[15], scheduler_cpu_state(1).R[15],
         nonblack[0], nonblack[1], varied[0], varied[1]);
}

uint32_t pad_to_key_mask(PadState* pad) {
    return vore::key_mask(g_config, padGetButtons(pad));
}

void flush_audio() {
    static int16_t buffer[2048 * 2];
    uint32_t frames = nds_spu_read_output(buffer, 2048);
    if (frames == 0) return;
    // Audio output lands in a later milestone; draining keeps the ring from
    // back-pressuring the mixer.
    (void)frames;
}

}  // namespace

int main(int argc, char** argv) {
    (void)argc;
    (void)argv;

    consoleInit(nullptr);
    std::printf("vore-nx -- Bowser's Inside Story static runtime\n\n");

    // Mount the SD card and the save/data archive.
    if (R_FAILED(fsInitialize())) {
        std::printf("fatal: filesystem service unavailable\n");
        consoleExit(nullptr);
        return 1;
    }
    fsdevMountSdmc();
    mkdir(kRoot, 0777);
    log_open();

    std::ifstream config_file(kConfigPath);
    std::string config_error;
    if (config_file && !vore::parse_config(config_file, g_config, config_error)) {
        vlog("fatal: %s", config_error.c_str());
        consoleExit(nullptr);
        return 1;
    }
    std::string save_path = std::string(kRoot) + "/" + g_config.save_file;
    // Retain the old development filename only when no explicit configuration
    // exists and the new ROM-matching default is absent. Never copy over it.
    if (!config_file.is_open()) {
        FILE* candidate = std::fopen(save_path.c_str(), "rb");
        if (candidate) std::fclose(candidate);
        else {
            std::string legacy = std::string(kRoot) + "/bis.sav";
            candidate = std::fopen(legacy.c_str(), "rb");
            if (candidate) { std::fclose(candidate); save_path = legacy; }
        }
    }
    std::string save_error;
    FILE* save = std::fopen(save_path.c_str(), "rb");
    const int save_open_error = errno;
    const bool had_save = save != nullptr;
    if (save) {
        const bool seek_ok = std::fseek(save, 0, SEEK_END) == 0;
        const long size = seek_ok ? std::ftell(save) : -1;
        std::fclose(save);
        if (size != 8192) {
            vlog("fatal: save must be raw 8192 bytes, found %ld; original untouched", size);
            consoleExit(nullptr);
            return 1;
        }
        // Preserve the imported original before the first possible game write.
        const std::string backup = save_path + ".import-backup";
        FILE* existing = std::fopen(backup.c_str(), "rb");
        if (existing) {
            const bool backup_ok = std::fseek(existing, 0, SEEK_END) == 0 && std::ftell(existing) == 8192;
            std::fclose(existing);
            if (!backup_ok) {
                vlog("fatal: import backup is incomplete; preserve it and repair manually");
                consoleExit(nullptr);
                return 1;
            }
        } else {
            const auto bytes = read_whole_file(save_path.c_str(), &save_error);
            FILE* out = bytes.size() == 8192 ? std::fopen(backup.c_str(), "wbx") : nullptr;
            bool copied = out && std::fwrite(bytes.data(), 1, bytes.size(), out) == bytes.size();
            if (out && std::fclose(out) != 0) copied = false;
            if (!copied) {
                vlog("fatal: cannot back up imported save; refusing to boot");
                consoleExit(nullptr);
                return 1;
            }
        }
        vlog("save: raw 8192-byte image accepted, import backup preserved");
    } else {
        if (save_open_error != ENOENT) {
            vlog("fatal: existing save cannot be opened (errno=%d); refusing to run", save_open_error);
            consoleExit(nullptr);
            return 1;
        }
        vlog("save: new raw EEPROM image will be created");
    }

    std::string error;
    std::vector<uint8_t> rom = read_whole_file(kRomPath, &error);
    if (rom.empty()) {
        vlog("fatal: %s", error.c_str());
        std::printf("fatal: %s\n\nPlace your own European CLJP cartridge\n"
                    "image at:\n  %s\n", error.c_str(), kRomPath);
        consoleExit(nullptr);
        return 1;
    }
    vlog("rom read: %zu bytes", rom.size());
    RomInfo info = check_rom(rom);
    if (!info.ok) {
        vlog("fatal: %s", info.error);
        std::printf("fatal: %s\n", info.error);
        consoleExit(nullptr);
        return 1;
    }
    std::printf("ROM: %.1f MiB, game code CLJP\n",
                static_cast<double>(rom.size()) / (1024.0 * 1024.0));
    vlog("game code CLJP accepted");

    const std::array<uint8_t, 6> mac = load_or_create_mac();
    std::vector<uint8_t> firmware =
        nds_generate_firmware(reinterpret_cast<const uint8_t*>(mac.data()));
    vlog("firmware generated: %zu bytes", firmware.size());
    std::printf("firmware: generated 128 KiB image (no retail dump)\n");

    std::printf("booting ...\n");
    consoleExit(nullptr);

    // Boot the machine.
    bus_init();
    cp15_reset();
    nds_io_reset();
    nds_io_load_firmware(firmware.data(), static_cast<uint32_t>(firmware.size()));
    // FreeBIOS (BSD-2-Clause) is the only boot path this build ships: it is
    // linked as data, never read from a retail console dump.
    const uint8_t* a9 = nds_freebios9;
    const uint8_t* a7 = nds_freebios7;
    bus_load_arm9_bios(a9, 4096);
    bus_load_arm7_bios(a7, 16384);

    // Loading occurs inside nds_io_load_cartridge, not in the path setter.
    // Setting this AFTER cartridge initialization silently ignored every save.
    nds_io_configure_cartridge_save({NdsCartridgeSaveType::Eeprom, 8192});
    nds_io_set_cartridge_save_path(save_path.c_str());

    if (!nds_io_load_cartridge(rom.data(), static_cast<uint32_t>(rom.size()),
                               a7, 16384)) {
        consoleInit(nullptr);
        std::printf("fatal: cartridge initialization failed\n");
        consoleExit(nullptr);
        return 1;
    }
    const uint8_t* loaded_save = nullptr;
    uint32_t loaded_size = 0;
    bool save_dirty = false;
    if (nds_io_cartridge_save_snapshot(&loaded_save, &loaded_size, &save_dirty)) {
        vlog("save: cartridge backing size=%u", loaded_size);
        if (had_save) {
            const auto expected = read_whole_file(save_path.c_str(), &save_error);
            if (expected.size() != loaded_size || std::memcmp(expected.data(), loaded_save, loaded_size) != 0) {
                vlog("fatal: loaded SRAM differs from imported save; refusing to run");
                consoleExit(nullptr);
                return 1;
            }
            vlog("save: loaded SRAM byte-identical to raw file");
        }
    }

    runtime_init(nullptr);
    live_overlay_runtime_reset();
    runtime_trace_reset();
    runtime_set_deep_trace(0);

    nds_register_dispatch(NDS_ARM9, g_dispatch_freebios_arm9,
                          g_dispatch_freebios_arm9_len, 0xFFFF0000u);
    nds_register_dispatch(NDS_ARM7, g_dispatch_freebios_arm7,
                          g_dispatch_freebios_arm7_len, 0x00000000u);

    // The generated registry re-checks the ROM identity itself; pass the
    // SHA-1 of the loaded image so a different cartridge never links a
    // mismatched bank.
    const char* sha1_hex = "5f35bfbf79a0947740795dd770d99e8eea3ac85e";

#if VORE_PRIVATE_BANKS
    const bool banks_ok = nds_register_configured_title_banks(sha1_hex);
    vlog("private banks registered: %s", banks_ok ? "yes" : "no");
    if (!banks_ok) {
        // No generated banks matched: Tier-3 interprets the cartridge.
        // Correct, just slower. Never silently substitute another title.
    }
#else
    (void)sha1_hex;
    vlog("public build: interpreter only");
#endif
    live_overlay_register_cached_banks();

    const uint32_t reset_cpsr = 0x13u | 0x80u | 0x40u;
    scheduler_init();
    scheduler_reset_cpu(0, 0xFFFF0000u, reset_cpsr);
    scheduler_reset_cpu(1, 0x00000000u, reset_cpsr);

    const uint32_t arm9_rom_offset =
        static_cast<uint32_t>(rom[0x20]) |
        (static_cast<uint32_t>(rom[0x21]) << 8) |
        (static_cast<uint32_t>(rom[0x22]) << 16) |
        (static_cast<uint32_t>(rom[0x23]) << 24);
    std::vector<uint8_t> secure_area(0x800);
    const bool has_secure_area =
        arm9_rom_offset >= 0x4000u && arm9_rom_offset < 0x8000u;
    if (has_secure_area && !nds_cart_secure_area_plaintext(secure_area.data())) {
        consoleInit(nullptr);
        std::printf("fatal: secure area could not be decrypted\n");
        consoleExit(nullptr);
        return 1;
    }

    NdsDirectBootInputs inputs;
    inputs.rom = rom.data();
    inputs.rom_size = static_cast<uint32_t>(rom.size());
    inputs.secure_area = has_secure_area ? secure_area.data() : nullptr;
    inputs.firmware = firmware.data();
    inputs.firmware_size = static_cast<uint32_t>(firmware.size());
    inputs.cart_chip_id = nds_cart_chip_id();
    inputs.arm9_bios_is_native = false;

    SwitchDirectBootMachine machine;
    std::string boot_error;
    vlog("direct boot: starting");
    if (!nds_direct_boot(machine, inputs, &boot_error)) {
        vlog("fatal: direct boot: %s", boot_error.c_str());
        consoleInit(nullptr);
        std::printf("fatal: direct boot: %s\n", boot_error.c_str());
        consoleExit(nullptr);
        return 1;
    }
    vlog("direct boot: done, first frame target %llu", (unsigned long long)kArm9CyclesPerFrame);

    nds_gpu3d_set_threaded(g_config.renderer_threads != 0);
    nds_gpu2d_set_threaded(g_config.renderer_threads != 0,
                          g_config.renderer_threads ? g_config.renderer_threads : 1);
    nds_gpu2d_set_adaptive_workers(0);
    if (g_config.video.aspect == vore::video::Aspect::Adaptive) {
        const bool wide = nds_gpu3d_set_output_width(342);
        vlog("experimental adaptive 3D width=342 enabled=%d; BIS 2D camera unpatched", wide);
    }
    vlog("layout: %s aspect=%d swapped=%d pace=%d renderer_threads=%u",
        g_config.video.orientation == vore::video::Orientation::Horizontal ? "horizontal" : "vertical",
        static_cast<int>(g_config.video.aspect), g_config.video.swapped, g_config.pace,
        g_config.renderer_threads);

    if (!video_init()) return 1;
    padConfigureInput(1, HidNpadStyleSet_NpadStandard);
    PadState pad;
    padInitializeDefault(&pad);
    hidInitializeTouchScreen();

    uint64_t target = 0;
    uint64_t frame = 0;
    uint32_t last_keys = 0xFFFu;
    bool last_touch = false;
    bool last_swap = false, last_mic = false;
    const u64 tick_frequency = armGetSystemTickFreq();
    u64 sample_start = armGetSystemTick();
    vore::FramePacer pacer(tick_frequency, sample_start);
    uint64_t sample_frame = 0;
    u64 sample_run_ticks = 0, sample_present_ticks = 0;
    while (appletMainLoop()) {
        padUpdate(&pad);
        const u64 buttons = padGetButtons(&pad);
        if (vore::held(buttons, g_config.exit)) {
            vlog("exit requested: mapped hotkey (buttons=0x%llX)",
                 (unsigned long long)buttons);
            break;
        }
        const bool swap = vore::held(buttons, g_config.swap);
        if (swap && !last_swap) {
            g_config.video.swapped = !g_config.video.swapped;
            vlog("input: screens swapped=%d", g_config.video.swapped);
        }
        last_swap = swap;
        vore::microphone::blowing = vore::held(buttons, g_config.mic);
        if (vore::microphone::blowing != last_mic) {
            vlog("input: microphone blowing=%d adc_conversions=%llu", vore::microphone::blowing,
                (unsigned long long)vore::microphone::conversions);
            last_mic = vore::microphone::blowing;
        }
        const uint32_t keys = pad_to_key_mask(&pad);
        nds_set_key_mask(keys);
        if (keys != last_keys) { vlog("input: keymask=0x%03X", keys); last_keys = keys; }
        HidTouchScreenState touch_state{};
        vore::video::Touch touch;
        if (hidGetTouchScreenStates(&touch_state, 1) > 0 && touch_state.count > 0) {
            touch = vore::video::bottom_touch(vore::video::arrange(1280, 720, g_config.video),
                touch_state.touches[0].x, touch_state.touches[0].y, g_presented_widths[1]);
        }
        nds_set_touch(touch.x, touch.y, touch.down);
        if (touch.down != last_touch) {
            vlog("input: touch %s (%u,%u)", touch.down ? "down" : "up", touch.x, touch.y);
            last_touch = touch.down;
        }
        target += kArm9CyclesPerFrame;
        if ((frame % 60u) == 0u) {
            vlog("frame %llu: scheduler_run target %llu", (unsigned long long)frame,
                 (unsigned long long)target);
        }
        const u64 run_start = armGetSystemTick();
        const SchedResult result = scheduler_run(target);
        sample_run_ticks += armGetSystemTick() - run_start;
        if (result.cycles[0] < target) {
            vlog("fatal: scheduler stopped before target=%llu cyc9=%llu "
                 "halt9=%d (%s) halt7=%d (%s)",
                 (unsigned long long)target,
                 (unsigned long long)result.cycles[0],
                 result.halted[0], result.reason[0] ? result.reason[0] : "none",
                 result.halted[1], result.reason[1] ? result.reason[1] : "none");
            log_progress(frame);
            break;
        }
        const double run_seconds =
            static_cast<double>(armGetSystemTick() - run_start) /
            static_cast<double>(armGetSystemTickFreq());
        if (run_seconds > 1.0) {
            // A single frame of DS time should never take this long. If the
            // scheduler gave up on a stalled ARM9 this line is the only trace
            // the Switch build can produce, so it carries the PCs.
            vlog("frame %llu took %.2fs: arm9 pc=0x%08X cyc=%llu | "
                 "arm7 pc=0x%08X cyc=%llu",
                 (unsigned long long)frame,
                 run_seconds, scheduler_cpu_state(0).R[15],
                 (unsigned long long)scheduler_cpu_cycles(0),
                 scheduler_cpu_state(1).R[15],
                 (unsigned long long)scheduler_cpu_cycles(1));
        }
        const u64 present_start = armGetSystemTick();
        present();
        sample_present_ticks += armGetSystemTick() - present_start;
        if ((frame % 60u) == 0u) log_progress(frame);
        flush_audio();
        ++frame;
        const u64 now = armGetSystemTick();
        if (frame % 120 == 0) {
            const double seconds = double(now - sample_start) / double(tick_frequency);
            const double frames = double(frame - sample_frame);
            const auto interpreted = tier3_stats();
            vlog("performance: %.2f guest frames/s scheduler=%.2fms present=%.2fms mic_adc=%llu",
                double(frame - sample_frame) / seconds,
                1000.0 * double(sample_run_ticks) / double(tick_frequency) / frames,
                1000.0 * double(sample_present_ticks) / double(tick_frequency) / frames,
                (unsigned long long)vore::microphone::conversions);
            vlog("dispatch: hits9=%llu absent9=%llu hits7=%llu absent7=%llu tier3_insn=%llu/%llu",
                (unsigned long long)g_nds_dispatch_stats[0].cache_hit,
                (unsigned long long)g_nds_dispatch_stats[0].cache_hit_absent,
                (unsigned long long)g_nds_dispatch_stats[1].cache_hit,
                (unsigned long long)g_nds_dispatch_stats[1].cache_hit_absent,
                (unsigned long long)interpreted.instructions[0],
                (unsigned long long)interpreted.instructions[1]);
            sample_frame = frame; sample_start = now;
            sample_run_ticks = 0; sample_present_ticks = 0;
        }
        const u64 sleep_ticks = pacer.advance(now);
        if (g_config.pace && sleep_ticks)
            svcSleepThread(static_cast<int64_t>(sleep_ticks * 1000000000ull / tick_frequency));
    }
    vlog("applet loop exited after %llu frames", (unsigned long long)frame);

    nds_io_flush_cartridge_save();
    framebufferClose(&g_framebuffer);
    if (g_log) { std::fclose(g_log); g_log = nullptr; }
    fsdevUnmountAll();
    fsExit();
    return 0;
}
