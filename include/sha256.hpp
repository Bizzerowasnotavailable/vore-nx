#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <string>

namespace vore {
class Sha256 {
public:
    void update(const void* data, std::size_t size);
    std::string finish();
private:
    void block(const std::uint8_t* data);
    std::array<std::uint32_t, 8> state_{{0x6a09e667, 0xbb67ae85, 0x3c6ef372,
        0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19}};
    std::array<std::uint8_t, 64> pending_{};
    std::uint64_t bytes_ = 0;
    std::size_t used_ = 0;
};
}
