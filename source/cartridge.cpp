#include "cartridge.hpp"
#include "sha256.hpp"
#include <algorithm>
#include <array>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <memory>
#include <sys/stat.h>
#ifdef _WIN32
#include <direct.h>
#else
#include <unistd.h>
#endif

namespace vore {
namespace {
struct CloseFile {
    void operator()(FILE* file) const noexcept { std::fclose(file); }
};
using File = std::unique_ptr<FILE, CloseFile>;
File open(const std::string& path, const char* mode) {
    return File(std::fopen(path.c_str(),mode));
}
Result fail(const std::string& message) { return {false,message}; }
bool tick(const Progress& p, const char* stage, std::uint64_t n, std::uint64_t total) {
    return !p || p(stage,n,total);
}
std::uint32_t u32(const std::uint8_t* p) {
    return p[0] | (std::uint32_t(p[1])<<8) | (std::uint32_t(p[2])<<16) |
        (std::uint32_t(p[3])<<24);
}
bool read_at(FILE* f, std::uint32_t offset, void* dst, std::size_t size) {
    return std::fseek(f,static_cast<long>(offset),SEEK_SET)==0 &&
        std::fread(dst,1,size,f)==size;
}
bool valid_range(std::uint32_t offset, std::uint32_t size, std::uint64_t end) {
    return std::uint64_t(offset)+size<=end;
}
Result hash_file(FILE* f, std::uint64_t size, std::string& digest, const Progress& p) {
    if (std::fseek(f,0,SEEK_SET)!=0) return fail("Cannot seek cartridge.");
    Sha256 hash;
    std::array<std::uint8_t,65536> buffer;
    for (std::uint64_t n=0; n<size;) {
        if (!tick(p,"Verifying ROM",n,size)) return fail("Cancelled; no installation committed.");
        auto want=static_cast<std::size_t>(std::min<std::uint64_t>(buffer.size(),size-n));
        if (std::fread(buffer.data(),1,want,f)!=want) return fail("Cannot read entire cartridge.");
        hash.update(buffer.data(),want);
        n+=want;
    }
    if (std::fgetc(f)!=EOF || std::ferror(f)) return fail("Cartridge changed size or read failed.");
    digest=hash.finish();
    return {true,{}};
}
Result inspect(FILE* f, Cartridge& c, const Progress& p) {
    c={};
    if (std::fseek(f,0,SEEK_END)!=0) return fail("Cannot seek cartridge.");
    auto length=std::ftell(f);
    if (length<512 || length>536870912L) return fail("Expected a DS cartridge of 512 bytes to 512 MiB.");
    c.size=static_cast<std::uint64_t>(length);
    std::array<std::uint8_t,512> h{};
    if (!read_at(f,0,h.data(),h.size())) return fail("Cannot read cartridge header.");
    if (h[0x12]!=0) return fail("Only original DS cartridges are supported (not DSi).");
    auto crc=std::uint16_t(h[0x15e] | (h[0x15f]<<8));
    if (nds_crc16(h.data(),0x15e)!=crc) return fail("Invalid DS header CRC16; dump may be damaged.");
    c.code.assign(reinterpret_cast<const char*>(h.data()+12),4);
    for (char ch:c.code) if (!((ch>='A'&&ch<='Z')||(ch>='0'&&ch<='9')))
        return fail("Invalid cartridge game code.");
    c.revision=h[0x1e];
    c.segments.push_back({"header.bin",0,512,0,0});
    for (unsigned cpu=0;cpu<2;++cpu) {
        auto off=0x20+cpu*16;
        Segment s{cpu?"arm7.bin":"arm9.bin",u32(&h[off]),u32(&h[off+12]),
            u32(&h[off+8]),u32(&h[off+4])};
        if (!s.size || s.offset<512 || !valid_range(s.offset,s.size,c.size))
            return fail("Invalid main CPU image range.");
        const auto end=std::uint64_t(s.load)+s.size;
        bool ram=s.load>=0x02000000 && end<=0x02400000;
        if (cpu) ram=ram || (s.load>=0x037f8000 && end<=0x03810000);
        auto entry=s.entry&~1u;
        if (!ram || entry<s.load || entry>=end || (entry&((s.entry&1)?1u:3u)))
            return fail("Invalid main CPU load/entry address.");
        c.segments.push_back(s);
    }
    const char* names[]={"fnt.bin","fat.bin","overlays9.bin","overlays7.bin"};
    for (unsigned i=0;i<4;++i) {
        auto off=0x40+i*8;
        Segment s{names[i],u32(&h[off]),u32(&h[off+4]),0,0};
        if (!valid_range(s.offset,s.size,c.size) || (s.size && s.offset<512))
            return fail("Invalid filesystem/overlay table range.");
        if (s.size>2*1024*1024) return fail("Filesystem table exceeds safety limit.");
        c.segments.push_back(s);
    }
    const auto fat=c.segments[4];
    if (fat.size%8) return fail("FAT length is not a multiple of 8.");
    c.files=fat.size/8;
    for (unsigned i=0;i<c.files;++i) {
        std::uint8_t row[8];
        if (!read_at(f,fat.offset+i*8,row,8)) return fail("Cannot read FAT.");
        auto begin=u32(row), end=u32(row+4);
        if (end<begin || !valid_range(begin,end-begin,c.size) || (end>begin && begin<512))
            return fail("FAT file extends outside cartridge.");
        char name[32];
        std::snprintf(name,sizeof(name),"file_%06u.bin",i);
        c.segments.push_back({name,begin,end-begin,0,0});
    }
    for (unsigned cpu=0;cpu<2;++cpu) {
        const auto& table=c.segments[5+cpu];
        if (table.size%32) return fail("Overlay table length is not a multiple of 32.");
        auto count=table.size/32;
        (cpu?c.arm7_overlays:c.arm9_overlays)=count;
        for (unsigned i=0;i<count;++i) {
            std::uint8_t row[32];
            if (!read_at(f,table.offset+i*32,row,32)) return fail("Cannot read overlay table.");
            if (u32(row+24)>=c.files) return fail("Overlay refers to a missing FAT file.");
            auto load=u32(row+4), size=u32(row+8), bss=u32(row+12);
            if (load<0x02000000 || std::uint64_t(load)+size+bss>0x02400000)
                return fail("Overlay memory range is invalid.");
        }
    }
    auto result=hash_file(f,c.size,c.sha256,p);
    if (!result) return result;
    c.supported=c.sha256==supported_sha256 && c.code=="CLJP" && c.revision==0;
    return {true,c.supported?"Verified CLJP revision 0.":"Valid structure; unsupported ROM hash. Installation disabled."};
}
int make_dir(const std::string& path) {
#ifdef _WIN32
    return _mkdir(path.c_str());
#else
    return mkdir(path.c_str(),0700);
#endif
}
void remove_dir(const std::string& path) {
#ifdef _WIN32
    _rmdir(path.c_str());
#else
    rmdir(path.c_str());
#endif
}
// Only paths created by this transaction are ever removed. No recursive delete.
struct Staging {
    std::string path;
    std::vector<std::string> created;
    bool committed=false;
    ~Staging() {
        if (committed) return;
        for (const auto& file:created) std::remove(file.c_str());
        remove_dir(path);
    }
};
}
std::uint16_t nds_crc16(const std::uint8_t* p, std::size_t size) {
    std::uint16_t crc=0xffff;
    for (std::size_t i=0;i<size;++i) {
        crc^=p[i];
        for (unsigned bit=0;bit<8;++bit) crc=std::uint16_t((crc>>1)^((crc&1)?0xa001:0));
    }
    return crc;
}
Result inspect_cartridge(const std::string& path, Cartridge& c, Progress progress) {
    c={};
    auto f=open(path,"rb");
    if (!f) return fail("Cannot open ROM. Put your own rom.nds at the documented path.");
    return inspect(f.get(),c,progress);
}
Result install_cartridge(const std::string& path, const std::string& root, Progress progress) {
    auto f=open(path,"rb");
    if (!f) return fail("Cannot open ROM.");
    Cartridge c;
    auto result=inspect(f.get(),c,progress);
    if (!result) return result;
    if (!c.supported) return fail("Unsupported ROM. Only exact CLJP revision 0 is currently accepted.");
    auto dest=root+"/"+c.sha256;
    struct stat st{};
    if (stat(dest.c_str(),&st)==0)
        return fail("Destination already exists; not overwritten or re-verified. Move it aside to reinstall.");
    Staging staging{dest+".partial",{},false};
    if (make_dir(staging.path)!=0) {
        // Do not let the guard remove a pre-existing directory.
        staging.committed=true;
        return fail("Cannot create staging directory. Check free space, parent directory, or an old .partial installation.");
    }
    auto manifest_path=staging.path+"/manifest.tsv";
    auto manifest=open(manifest_path,"wb");
    if (!manifest) return fail("Cannot create manifest.");
    staging.created.push_back(manifest_path);
    if (std::fprintf(manifest.get(),"vore-nx-install\t1\nrom-sha256\t%s\ngame-code\t%s\nrevision\t%u\n"
        "name\toffset\tsize\tload\tentry\tsha256\n",c.sha256.c_str(),c.code.c_str(),c.revision)<0)
        return fail("Cannot write manifest header.");
    std::uint64_t total=0,done=0;
    for (const auto& s:c.segments) total+=s.size;
    std::array<std::uint8_t,65536> buffer;
    for (const auto& s:c.segments) {
        if (!tick(progress,"Extracting",done,total)) return fail("Cancelled; no installation committed.");
        auto name=staging.path+"/"+s.name;
        auto out=open(name,"wb");
        if (!out) return fail("Cannot create extracted file. Check free space.");
        staging.created.push_back(name);
        if (std::fseek(f.get(),static_cast<long>(s.offset),SEEK_SET)!=0) return fail("Cannot seek input segment.");
        Sha256 hash;
        for (std::uint32_t n=0;n<s.size;) {
            if (!tick(progress,"Extracting",done,total)) return fail("Cancelled; no installation committed.");
            auto want=std::min<std::size_t>(buffer.size(),s.size-n);
            if (std::fread(buffer.data(),1,want,f.get())!=want ||
                std::fwrite(buffer.data(),1,want,out.get())!=want)
                return fail("Extraction I/O failed. Check cartridge and free space.");
            hash.update(buffer.data(),want);
            n+=static_cast<std::uint32_t>(want); done+=want;
        }
        if (std::fclose(out.release())!=0) return fail("Cannot flush extracted file.");
        auto digest=hash.finish();
        if (std::fprintf(manifest.get(),"%s\t%u\t%u\t%u\t%u\t%s\n",s.name.c_str(),
            s.offset,s.size,s.load,s.entry,digest.c_str())<0) return fail("Cannot write manifest.");
    }
    // Detect accidental source edits during extraction before committing output.
    std::string final_hash;
    result=hash_file(f.get(),c.size,final_hash,progress);
    if (!result) return result;
    if (final_hash!=c.sha256) return fail("ROM changed during installation; output discarded.");
    if (std::fclose(manifest.release())!=0) return fail("Cannot flush manifest.");
    if (std::rename(staging.path.c_str(),dest.c_str())!=0) return fail("Cannot commit installation directory.");
    staging.committed=true;
    return {true,"ROM extracted successfully. Game execution is not implemented yet."};
}
}
