// Minimal assertion helpers for the native C++ tests.

#pragma once

#include <iostream>
#include <string>

namespace pwb::test {

inline int& failures() {
    static int value = 0;
    return value;
}

inline void check(bool condition, const std::string& what) {
    if (!condition) {
        std::cerr << "FAIL " << what << "\n";
        ++failures();
    }
}

inline void check_equal(
    const std::string& actual,
    const std::string& expected,
    const std::string& what) {
    if (actual != expected) {
        std::cerr << "FAIL " << what << ": expected " << expected
                  << " got " << actual << "\n";
        ++failures();
    }
}

inline void check_equal(
    long long actual,
    long long expected,
    const std::string& what) {
    if (actual != expected) {
        std::cerr << "FAIL " << what << ": expected " << expected
                  << " got " << actual << "\n";
        ++failures();
    }
}

} // namespace pwb::test
