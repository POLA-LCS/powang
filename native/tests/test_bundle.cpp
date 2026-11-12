#include <array>
#include <cstddef>
#include <cstdint>
#include <string>

#include "pwb/bundle.hpp"
#include "pwb/error.hpp"
#include "pwb/sha256.hpp"
#include "test_support.hpp"

namespace {

std::string to_hex(const std::array<std::uint8_t, 32>& digest) {
    static const char* digits = "0123456789abcdef";
    std::string out;
    out.reserve(64);
    for (const std::uint8_t byte : digest) {
        out.push_back(digits[byte >> 4]);
        out.push_back(digits[byte & 0x0F]);
    }
    return out;
}

void test_sha256_vectors() {
    const std::array<std::uint8_t, 32> empty = pwb::sha256(nullptr, 0);
    pwb::test::check_equal(
        to_hex(empty),
        "e3b0c44298fc1c149afbf4c8996fb924"
        "27ae41e4649b934ca495991b7852b855",
        "sha256 empty");
    const std::string abc = "abc";
    const std::array<std::uint8_t, 32> digest = pwb::sha256(
        reinterpret_cast<const std::uint8_t*>(abc.data()), abc.size());
    pwb::test::check_equal(
        to_hex(digest),
        "ba7816bf8f01cfea414140de5dae2223"
        "b00361a396177a9cb410ff61f20015ad",
        "sha256 abc");
}

void test_bundle_rejects_malformed() {
    bool threw = false;
    try {
        (void)pwb::parse_bundle(nullptr, 0);
    } catch (const pwb::BundleError&) {
        threw = true;
    }
    pwb::test::check(threw, "short bundle is rejected");
    const std::uint8_t zeros[32] = {};
    threw = false;
    try {
        (void)pwb::parse_bundle(zeros, sizeof(zeros));
    } catch (const pwb::BundleError&) {
        threw = true;
    }
    pwb::test::check(threw, "bad bundle digest is rejected");
}

} // namespace

void run_bundle_tests() {
    test_sha256_vectors();
    test_bundle_rejects_malformed();
}
