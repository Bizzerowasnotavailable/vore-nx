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
#include <cstdio>
#include <cstdlib>
#include <cstring>
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

extern "C" {
extern const DispatchEntry g_dispatch_freebios_arm9[];
extern const unsigned g_dispatch_freebios_arm9_len;
extern const DispatchEntry g_dispatch_freebios_arm7[];
extern const unsigned g_dispatch_freebios_arm7_len;
}

namespace {

constexpr const char* kRoot = "sdmc:/switch/vore-nx";
constexpr const char* kRomPath = "sdmc:/switch/vore-nx/rom.nds";
constexpr const char* kSavePath = "sdmc:/switch/vore-nx/bis.sav";
constexpr const char* kMacPath = "sdmc:/switch/vore-nx/mac.bin";
constexpr const char* kFirmwarePath = "sdmc:/switch/vore-nx/firmware.bin";
constexpr const char* kLogPath = "sdmc:/switch/vore-nx/vore.log";

// ARM9 core clock 67.027964 MHz, 59.826 Hz refresh: one frame of DS time.
constexpr uint64_t kArm9CyclesPerFrame = 1120590;

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
    const bool drawn = vore::video::draw(base, stride_bytes, 1280, 720,
        nds_gpu2d_framebuffer(0), nds_gpu2d_framebuffer(1));
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
    uint32_t mask = 0x3FFu;  // all buttons released (active-low)
    const u64 held = padGetButtons(pad);
    if (held & HidNpadButton_A) mask &= ~(1u << 0);
    if (held & HidNpadButton_B) mask &= ~(1u << 1);
    if (held & HidNpadButton_Minus) mask &= ~(1u << 2);
    if (held & HidNpadButton_Plus) mask &= ~(1u << 3);
    if (held & HidNpadButton_Right) mask &= ~(1u << 4);
    if (held & HidNpadButton_Left) mask &= ~(1u << 5);
    if (held & HidNpadButton_Up) mask &= ~(1u << 6);
    if (held & HidNpadButton_Down) mask &= ~(1u << 7);
    if (held & HidNpadButton_R) mask &= ~(1u << 8);
    if (held & HidNpadButton_L) mask &= ~(1u << 9);
    return mask;
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
    log_open();

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

    if (!nds_io_load_cartridge(rom.data(), static_cast<uint32_t>(rom.size()),
                               a7, 16384)) {
        consoleInit(nullptr);
        std::printf("fatal: cartridge initialization failed\n");
        consoleExit(nullptr);
        return 1;
    }
    nds_io_set_cartridge_save_path(kSavePath);

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

    nds_gpu3d_set_threaded(false);
    nds_gpu2d_set_threaded(false, 1);
    nds_gpu2d_set_adaptive_workers(0);

    if (!video_init()) return 1;
    padConfigureInput(1, HidNpadStyleSet_NpadStandard);
    PadState pad;
    padInitializeDefault(&pad);
    hidInitializeTouchScreen();

    uint64_t target = 0;
    uint64_t frame = 0;
    uint32_t last_keys = 0x3FFu;
    bool last_touch = false;
    while (appletMainLoop()) {
        padUpdate(&pad);
        const u64 buttons = padGetButtons(&pad);
        if ((buttons & (HidNpadButton_StickL | HidNpadButton_StickR)) ==
            (HidNpadButton_StickL | HidNpadButton_StickR)) {
            vlog("exit requested: both stick clicks (buttons=0x%llX)",
                 (unsigned long long)buttons);
            break;
        }
        const uint32_t keys = pad_to_key_mask(&pad);
        nds_set_key_mask(keys);
        if (keys != last_keys) { vlog("input: keymask=0x%03X", keys); last_keys = keys; }
        HidTouchScreenState touch_state{};
        vore::video::Touch touch;
        if (hidGetTouchScreenStates(&touch_state, 1) > 0 && touch_state.count > 0) {
            touch = vore::video::bottom_touch(vore::video::stacked_layout(1280, 720),
                touch_state.touches[0].x, touch_state.touches[0].y);
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
        present();
        if ((frame % 60u) == 0u) log_progress(frame);
        flush_audio();
        ++frame;
    }
    vlog("applet loop exited after %llu frames", (unsigned long long)frame);

    nds_io_flush_cartridge_save();
    framebufferClose(&g_framebuffer);
    if (g_log) { std::fclose(g_log); g_log = nullptr; }
    fsdevUnmountAll();
    fsExit();
    return 0;
}
