#include "pwb/bigint.hpp"

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <stdexcept>

namespace pwb {
namespace {

constexpr std::uint64_t kBase = 1ull << 32;

int compare_magnitude_limbs(
    const std::vector<std::uint32_t>& left,
    const std::vector<std::uint32_t>& right) {
    if (left.size() != right.size()) {
        return left.size() < right.size() ? -1 : 1;
    }
    for (std::size_t index = left.size(); index-- > 0;) {
        if (left[index] != right[index]) {
            return left[index] < right[index] ? -1 : 1;
        }
    }
    return 0;
}

} // namespace

BigInt::BigInt(std::int64_t value) {
    if (value == 0) {
        return;
    }
    sign_ = value < 0 ? -1 : 1;
    const std::uint64_t magnitude = value < 0
        ? (~static_cast<std::uint64_t>(value) + 1ull)
        : static_cast<std::uint64_t>(value);
    magnitude_.push_back(static_cast<std::uint32_t>(magnitude & 0xFFFFFFFFull));
    const std::uint32_t high = static_cast<std::uint32_t>(magnitude >> 32);
    if (high != 0) {
        magnitude_.push_back(high);
    }
}

BigInt BigInt::parse_decimal(const std::string& text) {
    if (text.empty()) {
        throw std::invalid_argument("empty decimal integer");
    }
    std::size_t index = 0;
    int sign = 1;
    if (text[index] == '+' || text[index] == '-') {
        sign = text[index] == '-' ? -1 : 1;
        ++index;
    }
    if (index >= text.size()) {
        throw std::invalid_argument("decimal integer has no digits");
    }
    BigInt result;
    result.sign_ = 1;
    bool saw_digit = false;
    for (; index < text.size(); ++index) {
        const char character = text[index];
        if (character < '0' || character > '9') {
            throw std::invalid_argument("invalid decimal integer: " + text);
        }
        saw_digit = true;
        result.mul_small(10);
        result = result.add_small(static_cast<std::uint32_t>(character - '0'));
    }
    if (!saw_digit) {
        throw std::invalid_argument("decimal integer has no digits");
    }
    result.sign_ = result.magnitude_.empty() ? 0 : sign;
    result.normalize();
    return result;
}

std::string BigInt::format_decimal() const {
    if (sign_ == 0) {
        return "0";
    }
    BigInt copy = absolute();
    std::vector<std::uint32_t> groups;
    while (!copy.magnitude_.empty()) {
        groups.push_back(copy.divmod_small(1000000000u));
    }
    std::string out;
    if (sign_ < 0) {
        out.push_back('-');
    }
    out += std::to_string(groups.back());
    for (std::size_t index = groups.size() - 1; index-- > 0;) {
        char buffer[16];
        std::snprintf(buffer, sizeof(buffer), "%09u", groups[index]);
        out += buffer;
    }
    return out;
}

double BigInt::to_double() const {
    return std::strtod(format_decimal().c_str(), nullptr);
}

int BigInt::compare(const BigInt& other) const {
    if (sign_ != other.sign_) {
        return sign_ < other.sign_ ? -1 : 1;
    }
    if (sign_ == 0) {
        return 0;
    }
    const int magnitude = compare_magnitude_limbs(magnitude_, other.magnitude_);
    return sign_ < 0 ? -magnitude : magnitude;
}

bool BigInt::is_zero() const noexcept {
    return sign_ == 0;
}

bool BigInt::is_negative() const noexcept {
    return sign_ < 0;
}

BigInt BigInt::negate() const {
    BigInt result = *this;
    result.sign_ = -result.sign_;
    return result;
}

BigInt BigInt::absolute() const {
    BigInt result = *this;
    if (result.sign_ < 0) {
        result.sign_ = 1;
    }
    return result;
}

BigInt BigInt::add(const BigInt& other) const {
    if (sign_ == 0) {
        return other;
    }
    if (other.sign_ == 0) {
        return *this;
    }
    if (sign_ == other.sign_) {
        BigInt result = add_magnitude(*this, other);
        result.sign_ = sign_;
        return result;
    }
    const int magnitude = compare_magnitude_limbs(magnitude_, other.magnitude_);
    if (magnitude == 0) {
        return BigInt();
    }
    if (magnitude > 0) {
        BigInt result = subtract_magnitude(*this, other);
        result.sign_ = sign_;
        return result;
    }
    BigInt result = subtract_magnitude(other, *this);
    result.sign_ = other.sign_;
    return result;
}

BigInt BigInt::subtract(const BigInt& other) const {
    return add(other.negate());
}

BigInt BigInt::multiply(const BigInt& other) const {
    if (sign_ == 0 || other.sign_ == 0) {
        return BigInt();
    }
    BigInt result = multiply_magnitude(*this, other);
    result.sign_ = sign_ * other.sign_;
    return result;
}

std::pair<BigInt, BigInt> BigInt::divmod(const BigInt& divisor) const {
    if (divisor.sign_ == 0) {
        throw std::domain_error("BigInt division by zero");
    }
    if (sign_ == 0) {
        return {BigInt(), BigInt()};
    }
    const BigInt numerator = absolute();
    const BigInt denominator = divisor.absolute();
    if (compare_magnitude_limbs(numerator.magnitude_, denominator.magnitude_) < 0) {
        BigInt remainder = *this;
        return {BigInt(), remainder};
    }

    const std::size_t bits = numerator.bit_length();
    BigInt quotient;
    quotient.sign_ = 1;
    quotient.magnitude_.assign((bits + 31) / 32, 0);
    BigInt remainder;
    remainder.sign_ = 1;
    for (std::size_t position = bits; position-- > 0;) {
        remainder = remainder.shift_left_one();
        if (numerator.bit_at(position)) {
            remainder = remainder.add_small(1);
        }
        if (compare_magnitude_limbs(
                remainder.magnitude_, denominator.magnitude_) >= 0) {
            remainder = subtract_magnitude(remainder, denominator);
            quotient.set_bit(position);
        }
    }
    quotient.normalize();
    if (quotient.sign_ != 0) {
        quotient.sign_ = sign_ * divisor.sign_;
    }
    remainder.normalize();
    if (remainder.sign_ != 0) {
        remainder.sign_ = sign_;
    }
    return {quotient, remainder};
}

BigInt BigInt::divide(const BigInt& divisor) const {
    return divmod(divisor).first;
}

BigInt BigInt::remainder(const BigInt& divisor) const {
    return divmod(divisor).second;
}

void BigInt::normalize() {
    while (!magnitude_.empty() && magnitude_.back() == 0) {
        magnitude_.pop_back();
    }
    if (magnitude_.empty()) {
        sign_ = 0;
    }
}

std::size_t BigInt::bit_length() const {
    if (magnitude_.empty()) {
        return 0;
    }
    const std::uint32_t high = magnitude_.back();
    std::size_t bits = 0;
    std::uint32_t value = high;
    while (value != 0) {
        ++bits;
        value >>= 1;
    }
    return (magnitude_.size() - 1) * 32 + bits;
}

bool BigInt::bit_at(std::size_t index) const {
    const std::size_t limb = index / 32;
    if (limb >= magnitude_.size()) {
        return false;
    }
    return (magnitude_[limb] & (1u << (index % 32))) != 0;
}

void BigInt::set_bit(std::size_t index) {
    const std::size_t limb = index / 32;
    if (limb >= magnitude_.size()) {
        magnitude_.resize(limb + 1, 0);
    }
    magnitude_[limb] |= 1u << (index % 32);
}

BigInt BigInt::shift_left_one() const {
    BigInt result;
    if (sign_ == 0) {
        return result;
    }
    result.sign_ = 1;
    result.magnitude_.resize(magnitude_.size() + 1, 0);
    std::uint32_t carry = 0;
    for (std::size_t index = 0; index < magnitude_.size(); ++index) {
        const std::uint32_t value = magnitude_[index];
        result.magnitude_[index] = (value << 1) | carry;
        carry = value >> 31;
    }
    result.magnitude_[magnitude_.size()] = carry;
    result.normalize();
    return result;
}

BigInt BigInt::add_small(std::uint32_t value) const {
    BigInt result = *this;
    if (value == 0) {
        return result;
    }
    std::uint64_t carry = value;
    for (std::size_t index = 0; index < result.magnitude_.size() && carry; ++index) {
        const std::uint64_t sum =
            static_cast<std::uint64_t>(result.magnitude_[index]) + carry;
        result.magnitude_[index] = static_cast<std::uint32_t>(sum & 0xFFFFFFFFull);
        carry = sum >> 32;
    }
    if (carry != 0) {
        result.magnitude_.push_back(static_cast<std::uint32_t>(carry));
    }
    if (result.magnitude_.empty()) {
        result.sign_ = 0;
    } else if (result.sign_ == 0) {
        result.sign_ = 1;
    }
    return result;
}

void BigInt::mul_small(std::uint32_t factor) {
    if (sign_ == 0 || factor == 0) {
        magnitude_.clear();
        sign_ = 0;
        return;
    }
    std::uint64_t carry = 0;
    for (std::size_t index = 0; index < magnitude_.size(); ++index) {
        const std::uint64_t product =
            static_cast<std::uint64_t>(magnitude_[index]) * factor + carry;
        magnitude_[index] = static_cast<std::uint32_t>(product & 0xFFFFFFFFull);
        carry = product >> 32;
    }
    while (carry != 0) {
        magnitude_.push_back(static_cast<std::uint32_t>(carry & 0xFFFFFFFFull));
        carry >>= 32;
    }
}

std::uint32_t BigInt::divmod_small(std::uint32_t divisor) {
    std::uint64_t remainder = 0;
    for (std::size_t index = magnitude_.size(); index-- > 0;) {
        const std::uint64_t current =
            (remainder << 32) | static_cast<std::uint64_t>(magnitude_[index]);
        magnitude_[index] = static_cast<std::uint32_t>(current / divisor);
        remainder = current % divisor;
    }
    normalize();
    return static_cast<std::uint32_t>(remainder);
}

int BigInt::compare_magnitude(const BigInt& left, const BigInt& right) {
    return compare_magnitude_limbs(left.magnitude_, right.magnitude_);
}

BigInt BigInt::add_magnitude(const BigInt& left, const BigInt& right) {
    BigInt result;
    result.sign_ = 1;
    const std::size_t count = std::max(left.magnitude_.size(), right.magnitude_.size());
    result.magnitude_.resize(count, 0);
    std::uint64_t carry = 0;
    for (std::size_t index = 0; index < count; ++index) {
        const std::uint64_t a = index < left.magnitude_.size()
            ? left.magnitude_[index]
            : 0;
        const std::uint64_t b = index < right.magnitude_.size()
            ? right.magnitude_[index]
            : 0;
        const std::uint64_t sum = a + b + carry;
        result.magnitude_[index] = static_cast<std::uint32_t>(sum & 0xFFFFFFFFull);
        carry = sum >> 32;
    }
    if (carry != 0) {
        result.magnitude_.push_back(static_cast<std::uint32_t>(carry));
    }
    result.normalize();
    return result;
}

BigInt BigInt::subtract_magnitude(const BigInt& left, const BigInt& right) {
    BigInt result;
    result.sign_ = 1;
    result.magnitude_.resize(left.magnitude_.size(), 0);
    std::int64_t borrow = 0;
    for (std::size_t index = 0; index < left.magnitude_.size(); ++index) {
        const std::int64_t a = left.magnitude_[index];
        const std::int64_t b = index < right.magnitude_.size()
            ? static_cast<std::int64_t>(right.magnitude_[index])
            : 0;
        std::int64_t difference = a - b - borrow;
        if (difference < 0) {
            difference += static_cast<std::int64_t>(kBase);
            borrow = 1;
        } else {
            borrow = 0;
        }
        result.magnitude_[index] = static_cast<std::uint32_t>(difference);
    }
    result.normalize();
    return result;
}

BigInt BigInt::multiply_magnitude(const BigInt& left, const BigInt& right) {
    BigInt result;
    result.sign_ = 1;
    result.magnitude_.assign(left.magnitude_.size() + right.magnitude_.size(), 0);
    for (std::size_t i = 0; i < left.magnitude_.size(); ++i) {
        std::uint64_t carry = 0;
        for (std::size_t j = 0; j < right.magnitude_.size(); ++j) {
            const std::uint64_t current =
                static_cast<std::uint64_t>(left.magnitude_[i])
                    * right.magnitude_[j]
                + result.magnitude_[i + j]
                + carry;
            result.magnitude_[i + j] =
                static_cast<std::uint32_t>(current & 0xFFFFFFFFull);
            carry = current >> 32;
        }
        std::size_t index = i + right.magnitude_.size();
        while (carry != 0) {
            const std::uint64_t current =
                static_cast<std::uint64_t>(result.magnitude_[index]) + carry;
            result.magnitude_[index] =
                static_cast<std::uint32_t>(current & 0xFFFFFFFFull);
            carry = current >> 32;
            ++index;
        }
    }
    result.normalize();
    return result;
}

} // namespace pwb
