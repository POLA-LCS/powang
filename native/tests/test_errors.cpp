#include <stdexcept>
#include <string>

#include "pwb/errors.hpp"
#include "pwb/host.hpp"
#include "pwb/object.hpp"
#include "pwb/value.hpp"
#include "test_support.hpp"

namespace {

using pwb::FrameRecord;
using pwb::ErrorObject;
using pwb::Value;
using pwb::test::check;
using pwb::test::check_equal;

class TestHost : public pwb::Host {
public:
    void write(const std::string& text) override { output += text; }
    void write_error(const std::string& text) override { errors += text; }

    Value call_extern(
        std::string_view name,
        const Value* arguments,
        std::size_t argument_count,
        pwb::Arena& arena) override {
        if (name == "add" && argument_count == 2) {
            return pwb::make_int(arguments[0].i + arguments[1].i);
        }
        return pwb::Host::call_extern(
            name, arguments, argument_count, arena);
    }

    std::string output;
    std::string errors;
};

} // namespace

void run_error_tests() {
    FrameRecord frame;
    frame.name = "divide";
    frame.file = "program.po";
    frame.line = 10;
    frame.column = 4;
    check_equal(
        frame.render(), "at divide (program.po:10:4)", "frame render");

    FrameRecord no_line;
    no_line.name = "inner";
    no_line.file = "program.po";
    check_equal(
        no_line.render(), "at inner (program.po)", "frame render no line");

    ErrorObject error;
    error.kind = "TYPE";
    error.where = "builtin: fail";
    error.message = "Types doesn't match";
    error.details = {"expected str", "but int was encounter"};
    check_equal(
        error.base_text(),
        "[TYPE ERROR] (in builtin: fail) Types doesn't match:\n"
        "      | expected str\n"
        "      | but int was encounter",
        "error base text");
    check_equal(
        error.readable(), "[TYPE ERROR] Types doesn't match",
        "error readable");
    error.line = 3;
    check_equal(
        error.text(),
        "ln: 3 | [TYPE ERROR] (in builtin: fail) Types doesn't match:\n"
        "      | expected str\n"
        "      | but int was encounter",
        "error text with line");

    pwb::Arena arena;
    ErrorObject* identifier = pwb::error_identifier_not_found(
        arena, "access expression", "missing",
        {"module 'm' has no exported member 'missing'"});
    check_equal(
        identifier->base_text(),
        "[IDENTIFIER ERROR] (in access expression) doens't exists:\n"
        "      | missing\n"
        "      | module 'm' has no exported member 'missing'",
        "identifier helper text");
    ErrorObject* index = pwb::error_index_out_of_range(arena, 9, 2);
    check_equal(
        index->base_text(),
        "[INDEX ERROR] Out of range:\n"
        "      | index 9 out of range [0; 2)",
        "index helper text");

    const Value error_value = pwb::make_error_value(identifier);
    check_equal(
        pwb::format_value(error_value), identifier->readable(),
        "error value formatting");
    check(pwb::truthy(error_value), "error values are truthy");
    check(
        pwb::value_equal(error_value, error_value),
        "error values compare by identity");

    pwb::RefObject* reference = arena.allocate_reference();
    const Value reference_value = pwb::make_reference(reference);
    check_equal(
        pwb::format_value(reference_value), "<reference>",
        "reference formatting");
    check(
        pwb::is_reference(pwb::copy_value(arena, reference_value)),
        "references copy by identity");
    check(
        pwb::is_defined(reference_value),
        "reference values are defined");

    TestHost host;
    const Value extern_arguments[2] = {
        pwb::make_int(2), pwb::make_int(3),
    };
    const Value extern_result = host.call_extern(
        "add", extern_arguments, 2, arena);
    check_equal(
        extern_result.i, 5, "scalar extern host boundary");
    bool threw = false;
    try {
        (void)host.call_extern("missing", nullptr, 0, arena);
    } catch (const std::runtime_error&) {
        threw = true;
    }
    check(threw, "default host extern boundary is explicit");

    ErrorObject* override_error = arena.allocate_error();
    override_error->kind = "MODULE";
    override_error->text_override = "custom text";
    override_error->has_text_override = true;
    check_equal(
        override_error->text(), "custom text",
        "deferred error text override");
}
