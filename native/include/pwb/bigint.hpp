// Signed arbitrary precision integers for the native runtime.
//
// The representation is sign and magnitude. Magnitude limbs are little endian
// base 2^32 with no leading zero limb. The N1 VM uses BigInt for language
// integers that do not fit in int64. The full language has one integer type,
// so this is an internal storage detail, not a new public value type.

#pragma once

#include <cstdint>
#include <string>
#include <utility>
#include <vector>

namespace pwb {

class BigInt {
public:
    BigInt() = default;
    explicit BigInt(std::int64_t value);

    static BigInt parse_decimal(const std::string& text);

    std::string format_decimal() const;
    double to_double() const;

    int compare(const BigInt& other) const;
    bool is_zero() const noexcept;
    bool is_negative() const noexcept;

    BigInt negate() const;
    BigInt absolute() const;

    BigInt add(const BigInt& other) const;
    BigInt subtract(const BigInt& other) const;
    BigInt multiply(const BigInt& other) const;
    std::pair<BigInt, BigInt> divmod(const BigInt& divisor) const;
    BigInt divide(const BigInt& divisor) const;
    BigInt remainder(const BigInt& divisor) const;

private:
    int sign_ = 0;
    std::vector<std::uint32_t> magnitude_;

    void normalize();
    std::size_t bit_length() const;
    bool bit_at(std::size_t index) const;
    void set_bit(std::size_t index);
    BigInt shift_left_one() const;
    BigInt add_small(std::uint32_t value) const;
    void mul_small(std::uint32_t factor);
    std::uint32_t divmod_small(std::uint32_t divisor);

    static int compare_magnitude(const BigInt& left, const BigInt& right);
    static BigInt add_magnitude(const BigInt& left, const BigInt& right);
    static BigInt subtract_magnitude(const BigInt& left, const BigInt& right);
    static BigInt multiply_magnitude(const BigInt& left, const BigInt& right);
};

struct BigIntObject {
    BigInt value;
};

} // namespace pwb
