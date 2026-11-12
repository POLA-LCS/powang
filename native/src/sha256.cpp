#include "pwb/sha256.hpp"

#include <cstring>

namespace pwb {
namespace {

constexpr std::uint32_t kRound[64] = {
    0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u,
    0x3956c25bu, 0x59f111f1u, 0x923f82a4u, 0xab1c5ed5u,
    0xd807aa98u, 0x12835b01u, 0x243185beu, 0x550c7dc3u,
    0x72be5d74u, 0x80deb1feu, 0x9bdc06a7u, 0xc19bf174u,
    0xe49b69c1u, 0xefbe4786u, 0x0fc19dc6u, 0x240ca1ccu,
    0x2de92c6fu, 0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau,
    0x983e5152u, 0xa831c66du, 0xb00327c8u, 0xbf597fc7u,
    0xc6e00bf3u, 0xd5a79147u, 0x06ca6351u, 0x14292967u,
    0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu, 0x53380d13u,
    0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u,
    0xa2bfe8a1u, 0xa81a664bu, 0xc24b8b70u, 0xc76c51a3u,
    0xd192e819u, 0xd6990624u, 0xf40e3585u, 0x106aa070u,
    0x19a4c116u, 0x1e376c08u, 0x2748774cu, 0x34b0bcb5u,
    0x391c0cb3u, 0x4ed8aa4au, 0x5b9cca4fu, 0x682e6ff3u,
    0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u,
    0x90befffau, 0xa4506cebu, 0xbef9a3f7u, 0xc67178f2u,
};

std::uint32_t rotate_right(std::uint32_t value, int count) {
    return (value >> count) | (value << (32 - count));
}

void compress(std::uint32_t state[8], const std::uint8_t block[64]) {
    std::uint32_t schedule[64];
    for (int index = 0; index < 16; ++index) {
        schedule[index] =
            (static_cast<std::uint32_t>(block[index * 4]) << 24)
            | (static_cast<std::uint32_t>(block[index * 4 + 1]) << 16)
            | (static_cast<std::uint32_t>(block[index * 4 + 2]) << 8)
            | static_cast<std::uint32_t>(block[index * 4 + 3]);
    }
    for (int index = 16; index < 64; ++index) {
        const std::uint32_t s0 = rotate_right(schedule[index - 15], 7)
            ^ rotate_right(schedule[index - 15], 18)
            ^ (schedule[index - 15] >> 3);
        const std::uint32_t s1 = rotate_right(schedule[index - 2], 17)
            ^ rotate_right(schedule[index - 2], 19)
            ^ (schedule[index - 2] >> 10);
        schedule[index] = schedule[index - 16] + s0
            + schedule[index - 7] + s1;
    }
    std::uint32_t a = state[0];
    std::uint32_t b = state[1];
    std::uint32_t c = state[2];
    std::uint32_t d = state[3];
    std::uint32_t e = state[4];
    std::uint32_t f = state[5];
    std::uint32_t g = state[6];
    std::uint32_t h = state[7];
    for (int index = 0; index < 64; ++index) {
        const std::uint32_t s1 = rotate_right(e, 6)
            ^ rotate_right(e, 11) ^ rotate_right(e, 25);
        const std::uint32_t choice = (e & f) ^ ((~e) & g);
        const std::uint32_t temp1 = h + s1 + choice
            + kRound[index] + schedule[index];
        const std::uint32_t s0 = rotate_right(a, 2)
            ^ rotate_right(a, 13) ^ rotate_right(a, 22);
        const std::uint32_t majority = (a & b) ^ (a & c) ^ (b & c);
        const std::uint32_t temp2 = s0 + majority;
        h = g;
        g = f;
        f = e;
        e = d + temp1;
        d = c;
        c = b;
        b = a;
        a = temp1 + temp2;
    }
    state[0] += a;
    state[1] += b;
    state[2] += c;
    state[3] += d;
    state[4] += e;
    state[5] += f;
    state[6] += g;
    state[7] += h;
}

} // namespace

std::array<std::uint8_t, 32> sha256(
    const std::uint8_t* data, std::size_t size) {
    std::uint32_t state[8] = {
        0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
        0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u,
    };
    const std::uint64_t bit_length =
        static_cast<std::uint64_t>(size) * 8u;
    std::size_t offset = 0;
    while (size - offset >= 64) {
        compress(state, data + offset);
        offset += 64;
    }
    std::uint8_t block[128] = {};
    const std::size_t remaining = size - offset;
    if (remaining != 0) {
        std::memcpy(block, data + offset, remaining);
    }
    block[remaining] = 0x80u;
    const std::size_t padded =
        remaining < 56 ? std::size_t{64} : std::size_t{128};
    for (int index = 0; index < 8; ++index) {
        block[padded - 1 - index] = static_cast<std::uint8_t>(
            (bit_length >> (8 * index)) & 0xFFu);
    }
    compress(state, block);
    if (padded == 128) {
        compress(state, block + 64);
    }
    std::array<std::uint8_t, 32> digest{};
    for (int index = 0; index < 8; ++index) {
        digest[index * 4] =
            static_cast<std::uint8_t>((state[index] >> 24) & 0xFFu);
        digest[index * 4 + 1] =
            static_cast<std::uint8_t>((state[index] >> 16) & 0xFFu);
        digest[index * 4 + 2] =
            static_cast<std::uint8_t>((state[index] >> 8) & 0xFFu);
        digest[index * 4 + 3] =
            static_cast<std::uint8_t>(state[index] & 0xFFu);
    }
    return digest;
}

} // namespace pwb
