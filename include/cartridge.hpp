#pragma once
#include <cstddef>
#include <cstdint>
#include <functional>
#include <string>
#include <vector>

namespace vore {
inline constexpr char supported_sha256[] =
    "4d8a3ffa13ad525db85e596d576675860a816aa77560ca87c4505451c172c60b";
// Returning false cancels; callbacks also let the Switch frontend pump events.
using Progress = std::function<bool(const char*, std::uint64_t, std::uint64_t)>;
struct Segment {
    std::string name;
    std::uint32_t offset=0, size=0, load=0, entry=0;
};
struct Cartridge {
    std::string code, sha256;
    std::uint64_t size=0;
    unsigned revision=0, files=0, arm9_overlays=0, arm7_overlays=0;
    bool supported=false;
    std::vector<Segment> segments;
};
struct Result {
    bool ok=false;
    std::string message;
    explicit operator bool() const { return ok; }
};
std::uint16_t nds_crc16(const std::uint8_t* data, std::size_t size);
// Structural inspection is useful for tests/diagnostics, not a support claim.
Result inspect_cartridge(const std::string& path, Cartridge& cart, Progress progress={});
// Always re-inspects and requires the exact supported hash before any writes.
// root must already exist; creates root/<sha256> by staging + directory rename.
Result install_cartridge(const std::string& path, const std::string& root,
                         Progress progress={});
}
