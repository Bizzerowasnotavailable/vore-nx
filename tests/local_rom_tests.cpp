// Optional private integration test. Not part of ROM-free CI/CTest.
#include "cartridge.hpp"
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <string>

namespace {
unsigned checks=0;
void require(bool value, const char* what) {
    ++checks;
    if (!value) { std::fprintf(stderr,"FAIL: %s\n",what); std::exit(1); }
}
}
int main(int argc, char** argv) {
    if (argc!=3) {
        std::fprintf(stderr,"Usage: vore-local-tests LOCAL_ROM EXISTING_EMPTY_PRIVATE_OUTPUT_DIRECTORY\n");
        return 2;
    }
    const std::filesystem::path root=argv[2];
    require(std::filesystem::is_directory(root) && std::filesystem::is_empty(root),"require empty private test root");
    vore::Cartridge c;
    auto inspected=vore::inspect_cartridge(argv[1],c);
    require(bool(inspected) && c.supported,"exact local ROM identity");
    auto dest=root/c.sha256;
    auto staging=root/(c.sha256+".partial");
    auto cancelled=vore::install_cartridge(argv[1],root.string(),[](const char* stage, auto done, auto) {
        return std::string(stage)!="Extracting" || done==0;
    });
    require(!cancelled && cancelled.message.find("Cancelled")!=std::string::npos,"cancel during extraction");
    require(std::filesystem::is_empty(root),"cancel removes only its own staging files/directory");
    std::filesystem::create_directory(staging);
    { std::ofstream sentinel(staging/"user-marker.txt"); sentinel << "Preserve existing data."; }
    auto occupied=vore::install_cartridge(argv[1],root.string());
    require(!occupied,"pre-existing staging directory blocks install");
    require(std::filesystem::exists(staging/"user-marker.txt"),"existing staging contents preserved");
    std::filesystem::remove(staging/"user-marker.txt");
    std::filesystem::remove(staging);
    auto installed=vore::install_cartridge(argv[1],root.string());
    std::puts(installed.message.c_str());
    require(bool(installed),"install exact ROM");
    require(!std::filesystem::exists(staging),"successful install commits directory rename");
    require(std::filesystem::is_regular_file(dest/"manifest.tsv"),"manifest committed");
    require(std::filesystem::file_size(dest/"arm9.bin")==c.segments[1].size,"ARM9 size");
    require(std::filesystem::file_size(dest/"arm7.bin")==c.segments[2].size,"ARM7 size");
    unsigned count=0;
    for (const auto& entry:std::filesystem::directory_iterator(dest)) { (void)entry; ++count; }
    require(count==c.segments.size()+1,"all FAT files/tables and manifest extracted");
    { std::ofstream sentinel(dest/"user-marker.txt"); sentinel << "Preserve committed data."; }
    require(!vore::install_cartridge(argv[1],root.string()),"duplicate install refused");
    require(std::filesystem::exists(dest/"user-marker.txt"),"committed existing files preserved");
    std::filesystem::remove(dest/"user-marker.txt");
    std::printf("PASS: %u private integration checks. Extracted material retained in private output.\n",checks);
}
