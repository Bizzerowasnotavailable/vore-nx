#include "cartridge.hpp"
#include <cstdio>
#include <cstring>

int main(int argc, char** argv) {
    if ((argc!=3 && argc!=4) || (std::strcmp(argv[1],"inspect")!=0 &&
        std::strcmp(argv[1],"install")!=0)) {
        std::fprintf(stderr,"Usage: vore-rom inspect ROM\n       vore-rom install ROM EXISTING_PRIVATE_OUTPUT_DIRECTORY\n");
        return 2;
    }
    if (std::strcmp(argv[1],"install")==0) {
        if (argc!=4) return 2;
        auto result=vore::install_cartridge(argv[2],argv[3]);
        std::puts(result.message.c_str());
        return result?0:1;
    }
    if (argc!=3) return 2;
    vore::Cartridge c;
    auto result=vore::inspect_cartridge(argv[2],c);
    std::puts(result.message.c_str());
    if (!result) return 1;
    std::printf("code=%s revision=%u bytes=%llu\nsha256=%s\nfiles=%u arm9_overlays=%u arm7_overlays=%u\n",
        c.code.c_str(),c.revision,static_cast<unsigned long long>(c.size),c.sha256.c_str(),
        c.files,c.arm9_overlays,c.arm7_overlays);
    for (const auto& s:c.segments) {
        if (s.name.rfind("file_",0)==0) break;
        std::printf("%s offset=0x%08x size=0x%x load=0x%08x entry=0x%08x\n",
            s.name.c_str(),s.offset,s.size,s.load,s.entry);
    }
    return c.supported?0:3;
}
