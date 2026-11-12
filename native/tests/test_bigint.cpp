#include <stdexcept>
#include <string>

#include "pwb/bigint.hpp"
#include "test_support.hpp"

namespace {

using pwb::BigInt;
using pwb::test::check;
using pwb::test::check_equal;

void test_parse_and_format() {
    check_equal(BigInt::parse_decimal("0").format_decimal(), "0", "zero");
    check_equal(
        BigInt::parse_decimal("123456789012345678901234567890").format_decimal(),
        "123456789012345678901234567890",
        "large decimal round trip");
    check_equal(
        BigInt::parse_decimal("-9223372036854775808").format_decimal(),
        "-9223372036854775808",
        "int64 minimum round trip");
    check_equal(BigInt(-9223372036854775807LL - 1).format_decimal(),
                "-9223372036854775808", "int64 minimum constructor");
}

void test_power_of_two() {
    BigInt value(1);
    for (int index = 0; index < 200; ++index) {
        value = value.multiply(BigInt(2));
    }
    check_equal(
        value.format_decimal(),
        "1606938044258990275541962092341162602522202993782792835301376",
        "2 to the power 200");
    check(value.to_double() > 1.0e60, "2 to the power 200 to double");
}

void test_add_subtract_multiply() {
    check_equal(BigInt(5).add(BigInt(7)).format_decimal(), "12", "add");
    check_equal(BigInt(5).subtract(BigInt(7)).format_decimal(), "-2", "subtract");
    check_equal(BigInt(7).subtract(BigInt(5)).format_decimal(), "2", "subtract order");
    check_equal(
        BigInt(123456789).multiply(BigInt(987654321)).format_decimal(),
        "121932631112635269", "multiply");
    check_equal(
        BigInt(-5).multiply(BigInt(7)).format_decimal(), "-35",
        "multiply sign");
    check_equal(
        BigInt::parse_decimal("999999999999999999999")
            .add(BigInt(1))
            .format_decimal(),
        "1000000000000000000000", "carry");
}

void test_compare() {
    check(BigInt(5).compare(BigInt(7)) < 0, "compare less");
    check(BigInt(7).compare(BigInt(5)) > 0, "compare greater");
    check(BigInt(7).compare(BigInt(7)) == 0, "compare equal");
    check(BigInt(-7).compare(BigInt(5)) < 0, "compare negative");
    check(BigInt(-5).compare(BigInt(-7)) > 0, "compare both negative");
}

void test_division() {
    const auto a = BigInt(7).divmod(BigInt(3));
    check_equal(a.first.format_decimal(), "2", "7 divided by 3");
    check_equal(a.second.format_decimal(), "1", "7 remainder 3");

    const auto b = BigInt(-7).divmod(BigInt(3));
    check_equal(b.first.format_decimal(), "-2", "-7 divided by 3");
    check_equal(b.second.format_decimal(), "-1", "-7 remainder 3");

    const auto c = BigInt(7).divmod(BigInt(-3));
    check_equal(c.first.format_decimal(), "-2", "7 divided by -3");
    check_equal(c.second.format_decimal(), "1", "7 remainder -3");

    const auto d = BigInt(-7).divmod(BigInt(-3));
    check_equal(d.first.format_decimal(), "2", "-7 divided by -3");
    check_equal(d.second.format_decimal(), "-1", "-7 remainder -3");

    const auto e = BigInt(5).divmod(BigInt(7));
    check_equal(e.first.format_decimal(), "0", "5 divided by 7");
    check_equal(e.second.format_decimal(), "5", "5 remainder 7");

    bool threw = false;
    try {
        (void)BigInt(1).divmod(BigInt(0));
    } catch (const std::domain_error&) {
        threw = true;
    }
    check(threw, "division by zero");
}

void test_large_division() {
    const BigInt numerator = BigInt::parse_decimal(
        "1606938044258990275541962092341162602522202993782792835301376");
    const BigInt divisor = BigInt::parse_decimal("123456789");
    const auto result = numerator.divmod(divisor);
    const BigInt rebuilt = result.first.multiply(divisor).add(result.second);
    check_equal(rebuilt.format_decimal(), numerator.format_decimal(),
                "large division identity");
    check(result.second.compare(divisor.absolute()) < 0,
          "large division remainder bound");
}

} // namespace

void run_value_tests();
void run_bundle_tests();
void run_error_tests();
void run_task_tests();

int main() {
    test_parse_and_format();
    test_power_of_two();
    test_add_subtract_multiply();
    test_compare();
    test_division();
    test_large_division();
    run_value_tests();
    run_bundle_tests();
    run_error_tests();
    run_task_tests();
    return pwb::test::failures() == 0 ? 0 : 1;
}
