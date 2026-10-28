#include "cartridge.hpp"
#include "sha256.hpp"
#include <array>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <string>
#include <vector>

namespace {
unsigned checks=0;
void require(bool value, const char* what) {
    ++checks;
    if (!value) { std::fprintf(stderr,"FAIL: %s\n",what); std::exit(1); }
}
void put32(std::vector<std::uint8_t>& v, std::size_t off, std::uint32_t n) {
    for (unsigned i=0;i<4;++i) v[off+i]=std::uint8_t(n>>(8*i));
}
void fix_crc(std::vector<std::uint8_t>& v) {
    auto crc=vore::nds_crc16(v.data(),0x15e);
    v[0x15e]=std::uint8_t(crc); v[0x15f]=std::uint8_t(crc>>8);
}
std::vector<std::uint8_t> fixture() {
    // Entirely synthetic: no Nintendo logo, code, names, or other ROM bytes.
    std::vector<std::uint8_t> v(16384);
    v[12]='T';v[13]='E';v[14]='S';v[15]='T';
    put32(v,0x20,0x200); put32(v,0x24,0x02000000);
    put32(v,0x28,0x02000000); put32(v,0x2c,0x40);
    put32(v,0x30,0x400); put32(v,0x34,0x02380000);
    put32(v,0x38,0x02380000); put32(v,0x3c,0x40);
    put32(v,0x48,0x700); put32(v,0x4c,8);
    put32(v,0x50,0x900); put32(v,0x54,32);
    put32(v,0x700,0x800); put32(v,0x704,0x900);
    put32(v,0x904,0x02010000); put32(v,0x908,256); put32(v,0x90c,128);
    for (std::size_t i=0x800;i<0x900;++i) v[i]=std::uint8_t(i);
    fix_crc(v);
    return v;
}
void write(const std::string& path, const std::vector<std::uint8_t>& v) {
    FILE* f=std::fopen(path.c_str(),"wb"); require(f!=nullptr,"open fixture");
    require(std::fwrite(v.data(),1,v.size(),f)==v.size(),"write fixture");
    require(std::fclose(f)==0,"close fixture");
}
}
int main() {
    vore::Sha256 empty;
    require(empty.finish()=="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","SHA256 empty");
    vore::Sha256 abc; abc.update("abc",3);
    require(abc.finish()=="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad","SHA256 abc");
    vore::Sha256 million;
    std::string chunk(1000,'a');
    for (unsigned i=0;i<1000;++i) million.update(chunk.data(),chunk.size());
    require(million.finish()=="cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0","SHA256 multi-block");
    for (unsigned size=0;size<200;++size) {
        std::string input(size,'x');
        vore::Sha256 whole,split;
        whole.update(input.data(),input.size());
        for (char c:input) split.update(&c,1);
        require(whole.finish()==split.finish(),"SHA256 streaming/padding boundaries");
    }
    require(vore::nds_crc16(reinterpret_cast<const std::uint8_t*>("123456789"),9)==0x4b37,"CRC16 standard vector");
    auto dir=std::filesystem::temp_directory_path()/
        ("vore-nx-tests-"+std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
    require(std::filesystem::create_directory(dir),"create isolated fixture directory");
    auto path=(dir/"synthetic.nds").string();
    vore::Cartridge c;
    auto good=fixture();
    write(path,good);
    require(bool(vore::inspect_cartridge(path,c)),"inspect synthetic cartridge");
    require(c.files==1 && c.arm9_overlays==1 && c.arm7_overlays==0,"filesystem inventory");
    require(c.segments.size()==8 && c.segments.back().name=="file_000000.bin","numeric asset names");
    require(!c.supported,"synthetic cartridge cannot pass exact hash gate");
    require(!vore::install_cartridge(path,dir.string()),"unsupported image cannot install");
    require(!std::filesystem::exists(dir/(c.sha256+".partial")),"unsupported install wrote nothing");
    require(!vore::inspect_cartridge(path,c,[](const char*,auto,auto){return false;}),"verification cancellation");
    auto bad=good;bad[0]=1;write(path,bad);
    require(!vore::inspect_cartridge(path,c),"bad header CRC rejected");
    bad=good;put32(bad,0x20,0xfffffff0);fix_crc(bad);write(path,bad);
    require(!vore::inspect_cartridge(path,c),"overflowing CPU ROM range rejected");
    bad=good;put32(bad,0x28,0xfffffff0);fix_crc(bad);write(path,bad);
    require(!vore::inspect_cartridge(path,c),"overflowing CPU RAM range rejected");
    bad=good;put32(bad,0x24,0x02001000);fix_crc(bad);write(path,bad);
    require(!vore::inspect_cartridge(path,c),"entry outside image rejected");
    bad=good;put32(bad,0x4c,9);fix_crc(bad);write(path,bad);
    require(!vore::inspect_cartridge(path,c),"unaligned FAT rejected");
    bad=good;put32(bad,0x704,0x7ff);write(path,bad);
    require(!vore::inspect_cartridge(path,c),"backwards FAT range rejected");
    bad=good;put32(bad,0x704,0x100000);write(path,bad);
    require(!vore::inspect_cartridge(path,c),"FAT outside ROM rejected");
    bad=good;put32(bad,0x918,1);write(path,bad);
    require(!vore::inspect_cartridge(path,c),"overlay missing file rejected");
    bad=good;put32(bad,0x90c,0xffffffff);write(path,bad);
    require(!vore::inspect_cartridge(path,c),"overflowing overlay BSS rejected");
    bad=good;bad[0x12]=2;fix_crc(bad);write(path,bad);
    require(!vore::inspect_cartridge(path,c),"DSi image rejected");
    bad.resize(128);write(path,bad);
    require(!vore::inspect_cartridge(path,c),"truncated header rejected");
    require(!vore::inspect_cartridge((dir/"absent.nds").string(),c),"missing cartridge handled");
    std::filesystem::remove(path);
    std::filesystem::remove(dir);
    std::printf("PASS: %u checks (synthetic fixtures only).\n",checks);
}
