// Error types for the native runtime.
//
// Language errors are not represented by these types. These exceptions cover
// a malformed image, an invalid instruction stream, a verifier rejection and
// an unsupported native operation in the N0 slice.

#pragma once

#include <stdexcept>
#include <string>

namespace pwb {

class ImageError : public std::runtime_error {
public:
    explicit ImageError(const std::string& message) : std::runtime_error(message) {}
};

class VerificationError : public std::runtime_error {
public:
    explicit VerificationError(const std::string& message)
        : std::runtime_error(message) {}
};

class DecodeError : public std::runtime_error {
public:
    explicit DecodeError(const std::string& message) : std::runtime_error(message) {}
};

class RuntimeError : public std::runtime_error {
public:
    explicit RuntimeError(const std::string& message) : std::runtime_error(message) {}
};

} // namespace pwb
