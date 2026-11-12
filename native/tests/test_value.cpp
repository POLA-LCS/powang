#include <string>
#include <type_traits>

#include "pwb/bigint.hpp"
#include "pwb/error.hpp"
#include "pwb/object.hpp"
#include "pwb/value.hpp"
#include "test_support.hpp"

namespace {

using pwb::ArrayObject;
using pwb::BigInt;
using pwb::BigIntObject;
using pwb::FunctionObject;
using pwb::RuntimeError;
using pwb::Tag;
using pwb::Value;
using pwb::test::check;
using pwb::test::check_equal;

} // namespace

void run_value_tests() {
    static_assert(sizeof(Value) == 16, "Value must stay 16 bytes");
    static_assert(
        std::is_trivially_copyable<Value>::value,
        "Value must stay trivially copyable");

    const Value nova = pwb::make_nova();
    check(nova.tag == Tag::Nova, "nova tag");
    check_equal(pwb::format_value(nova), "nova", "nova format");

    const Value integer = pwb::make_int(-5);
    check(integer.tag == Tag::Int, "int tag");
    check_equal(pwb::format_value(integer), "-5", "int format");
    check(pwb::truthy(integer), "non zero int truthy");
    check(!pwb::truthy(pwb::make_int(0)), "zero int falsey");

    const Value number = pwb::make_num(2.5);
    check(number.tag == Tag::Num, "num tag");
    check_equal(pwb::format_value(number), "2.5", "num format");

    const Value boolean = pwb::make_bool(true);
    check(boolean.tag == Tag::Bool, "bool tag");
    check_equal(pwb::format_value(boolean), "true", "bool format");

    const Value character = pwb::make_char(U'A');
    check(character.tag == Tag::Char, "char tag");
    check_equal(pwb::format_value(character), "A", "char format");

    BigIntObject big;
    big.value = BigInt::parse_decimal("123456789012345678901234567890");
    const Value bigint = pwb::make_bigint(&big);
    check(bigint.tag == Tag::BigInt, "bigint tag");
    check_equal(pwb::format_value(bigint),
                "123456789012345678901234567890", "bigint format");
    check(pwb::truthy(bigint), "non zero bigint truthy");
    BigIntObject zero;
    check(!pwb::truthy(pwb::make_bigint(&zero)), "zero bigint falsey");

    ArrayObject array;
    array.items.push_back(pwb::make_int(1));
    const Value array_value = pwb::make_array(&array);
    check(array_value.tag == Tag::Arr, "array tag");
    check(pwb::is_array(array_value), "array predicate");
    check(pwb::truthy(array_value), "array truthy");
    check_equal(pwb::format_value(array_value), "[1]", "array print");

    const Value spread_value = pwb::make_spread(&array);
    check(spread_value.tag == Tag::Spread, "spread tag");
    check(pwb::is_spread(spread_value), "spread predicate");

    FunctionObject function;
    const Value function_value = pwb::make_function(&function);
    check(function_value.tag == Tag::Fun, "function tag");
    check(pwb::is_function(function_value), "function predicate");
    check(pwb::truthy(function_value), "function truthy");
    bool function_print_threw = false;
    try {
        (void)pwb::format_value(function_value);
    } catch (const RuntimeError&) {
        function_print_threw = true;
    }
    check(function_print_threw, "function print is not implemented in N1");
}
