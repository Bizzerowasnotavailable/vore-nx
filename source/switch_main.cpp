#include "cartridge.hpp"
#include <switch.h>
#include <cstdio>
#include <cstring>
#include <sys/stat.h>

namespace {
constexpr char rom[]="sdmc:/switch/vore-nx/rom.nds";
constexpr char root[]="sdmc:/switch/vore-nx/data";
PadState pad;
bool progress(const char* stage, std::uint64_t done, std::uint64_t total) {
    if (!appletMainLoop()) return false;
    padUpdate(&pad);
    if (padGetButtonsDown(&pad)&HidNpadButton_B) return false;
    // Update only on a new percentage to keep hashing/extraction responsive.
    static unsigned old=101;
    static const char* old_stage=nullptr;
    auto percent=total?static_cast<unsigned>(done*100/total):100;
    if (percent!=old || old_stage!=stage) {
        std::printf("\x1b[20;1H\x1b[2K%s: %u%%  (B: cancel)",stage,percent);
        consoleUpdate(nullptr);
        old=percent; old_stage=stage;
    }
    return true;
}
void screen(const std::string& message, const vore::Cartridge* c=nullptr) {
    consoleClear();
    std::printf("vore-nx 0.1.0 - ROM preparation milestone\n\n"
        "NOT PLAYABLE: DS execution backend is not implemented.\n"
        "No Nintendo code, graphics, sound, BIOS or firmware included.\n\n"
        "ROM: %s\n\n"
        "A: verify ROM    X: verify + extract    +: exit\n"
        "B during work: cancel\n\n%s\n",rom,message.c_str());
    if (c) std::printf("\nCode: %s  Revision: %u  FAT files: %u\n"
        "ARM9 overlays: %u  ARM7 overlays: %u\n"
        "Exact supported hash: %s\n",c->code.c_str(),c->revision,c->files,
        c->arm9_overlays,c->arm7_overlays,c->supported?"yes":"no");
    consoleUpdate(nullptr);
}
}
int main(int argc, char** argv) {
    consoleInit(nullptr);
    padConfigureInput(1,HidNpadStyleSet_NpadStandard);
    padInitializeDefault(&pad);
    screen("Use a cartridge dump you are entitled to use. No downloads provided.");
    // Test-only launch argument runs the same validation path without controller
    // automation. It never installs or writes ROM data.
    if (argc>1 && std::strcmp(argv[1],"--self-check")==0) {
        vore::Cartridge c;
        auto result=vore::inspect_cartridge(rom,c,progress);
        screen(result.message,result?&c:nullptr);
    }
    while (appletMainLoop()) {
        padUpdate(&pad);
        auto down=padGetButtonsDown(&pad);
        if (down&HidNpadButton_Plus) break;
        if (down&HidNpadButton_A) {
            vore::Cartridge c;
            auto result=vore::inspect_cartridge(rom,c,progress);
            screen(result.message,result?&c:nullptr);
        }
        if (down&HidNpadButton_X) {
            // These are dedicated application directories; existing paths are
            // never recursively deleted, and committed installs are immutable.
            mkdir("sdmc:/switch",0700);
            mkdir("sdmc:/switch/vore-nx",0700);
            mkdir(root,0700);
            auto result=vore::install_cartridge(rom,root,progress);
            screen(result.message);
        }
        consoleUpdate(nullptr);
    }
    consoleExit(nullptr);
    return 0;
}
