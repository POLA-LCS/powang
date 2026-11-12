#include "pwb/meta.hpp"

#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>

#include "pwb/error.hpp"
#include "pwb/image.hpp"

namespace pwb {
namespace {

constexpr std::uint32_t kAbsentIndex = 0xFFFFFFFFu;
constexpr std::uint32_t kMaxRecords = 1000000u;

class MetaReader {
public:
    MetaReader(const std::uint8_t* data, std::size_t size)
        : data_(data), size_(size) {}

    std::uint8_t u8(const char* what) {
        return take(1, what)[0];
    }

    std::uint16_t u16(const char* what) {
        const std::uint8_t* bytes = take(2, what);
        return static_cast<std::uint16_t>(
            static_cast<std::uint16_t>(bytes[0])
            | (static_cast<std::uint16_t>(bytes[1]) << 8));
    }

    std::uint32_t u32(const char* what) {
        const std::uint8_t* bytes = take(4, what);
        return static_cast<std::uint32_t>(bytes[0])
            | (static_cast<std::uint32_t>(bytes[1]) << 8)
            | (static_cast<std::uint32_t>(bytes[2]) << 16)
            | (static_cast<std::uint32_t>(bytes[3]) << 24);
    }

    std::int32_t i32(const char* what) {
        return static_cast<std::int32_t>(u32(what));
    }

    std::string string(const char* what) {
        const std::uint32_t length = u32(what);
        const std::uint8_t* bytes = take(length, what);
        return std::string(
            reinterpret_cast<const char*>(bytes),
            static_cast<std::size_t>(length));
    }

    std::size_t remaining() const {
        return size_ - offset_;
    }

private:
    const std::uint8_t* take(std::size_t count, const char* what) {
        if (count > size_ - offset_) {
            throw MetadataError(
                std::string("truncated PWBM metadata while reading ")
                + what + " at offset " + std::to_string(offset_));
        }
        const std::uint8_t* result = data_ + offset_;
        offset_ += count;
        return result;
    }

    const std::uint8_t* data_;
    std::size_t size_;
    std::size_t offset_ = 0;
};

std::string hex_hash(const std::array<std::uint8_t, 32>& hash) {
    std::ostringstream out;
    out << std::hex << std::setfill('0');
    for (const std::uint8_t byte : hash) {
        out << std::setw(2) << static_cast<unsigned int>(byte);
    }
    return out.str();
}

} // namespace

Meta parse_meta(const std::uint8_t* data, std::size_t size) {
    if (data == nullptr && size != 0) {
        throw MetadataError("PWBM data is null");
    }
    MetaReader reader(data, size);
    const std::uint8_t first = reader.u8("magic");
    const std::uint8_t second = reader.u8("magic");
    const std::uint8_t third = reader.u8("magic");
    const std::uint8_t fourth = reader.u8("magic");
    if (first != 'P' || second != 'W' || third != 'B' || fourth != 'M') {
        throw MetadataError("invalid PWBM magic");
    }
    Meta meta;
    meta.version = reader.u16("version");
    if (meta.version != 1) {
        throw MetadataError(
            "unsupported PWBM version: " + std::to_string(meta.version));
    }
    meta.flags = reader.u16("flags");
    const std::uint32_t function_count = reader.u32("function count");
    const std::uint32_t type_count = reader.u32("type spec count");
    if (function_count > kMaxRecords || type_count > kMaxRecords) {
        throw MetadataError("PWBM record count is too large");
    }
    for (std::uint8_t& byte : meta.image_hash) {
        byte = reader.u8("image hash");
    }

    meta.types.reserve(type_count);
    for (std::uint32_t index = 0; index < type_count; ++index) {
        MetaTypeSpec type;
        const std::uint8_t kind = reader.u8("type kind");
        if (kind > static_cast<std::uint8_t>(MetaTypeKind::Param)) {
            throw MetadataError("unknown PWBM type kind: " + std::to_string(kind));
        }
        type.kind = static_cast<MetaTypeKind>(kind);
        type.name = reader.string("type name");
        type.nominal = reader.string("type nominal");
        type.flags = reader.u8("type flags");
        const std::uint32_t argument_count = reader.u32("type argument count");
        if (argument_count > kMaxRecords) {
            throw MetadataError("PWBM type argument count is too large");
        }
        type.args.reserve(argument_count);
        for (std::uint32_t position = 0; position < argument_count; ++position) {
            type.args.push_back(reader.u32("type argument"));
        }
        const std::uint32_t parameter_count = reader.u32("type parameter count");
        if (parameter_count > kMaxRecords) {
            throw MetadataError("PWBM type parameter count is too large");
        }
        type.params.reserve(parameter_count);
        for (std::uint32_t position = 0; position < parameter_count; ++position) {
            type.params.push_back(reader.u32("type parameter"));
        }
        type.returns = reader.u32("type returns");
        meta.types.push_back(std::move(type));
    }

    meta.functions.reserve(function_count);
    for (std::uint32_t index = 0; index < function_count; ++index) {
        FunctionMetadata function;
        function.name = reader.string("function name");
        function.code_index = reader.u32("function code index");
        function.min_argc = reader.u32("function min argc");
        function.flags = reader.u32("function flags");
        function.variadic_index = reader.i32("function variadic index");
        const std::uint32_t parameter_count = reader.u32("function parameter count");
        if (parameter_count > kMaxRecords) {
            throw MetadataError("PWBM function parameter count is too large");
        }
        function.parameters.reserve(parameter_count);
        for (std::uint32_t position = 0; position < parameter_count; ++position) {
            MetaParameter parameter;
            parameter.name = reader.string("parameter name");
            parameter.type_index = reader.u32("parameter type index");
            parameter.flags = reader.u8("parameter flags");
            parameter.default_index = reader.i32("parameter default index");
            function.parameters.push_back(std::move(parameter));
        }
        const std::uint32_t type_parameter_count =
            reader.u32("function type parameter count");
        if (type_parameter_count > kMaxRecords) {
            throw MetadataError("PWBM function type parameter count is too large");
        }
        function.type_parameters.reserve(type_parameter_count);
        for (std::uint32_t position = 0; position < type_parameter_count; ++position) {
            function.type_parameters.push_back(reader.string("type parameter name"));
        }
        function.function_type = reader.string("function type");
        const std::uint8_t has_lambda = reader.u8("function lambda presence");
        if (has_lambda > 1) {
            throw MetadataError("invalid PWBM lambda presence");
        }
        if (has_lambda == 1) {
            function.lambda_name = reader.string("function lambda name");
        }
        const std::uint32_t defaults_count = reader.u32("function defaults count");
        if (defaults_count > kMaxRecords) {
            throw MetadataError("PWBM function default count is too large");
        }
        function.defaults.reserve(defaults_count);
        for (std::uint32_t position = 0; position < defaults_count; ++position) {
            function.defaults.push_back(reader.i32("function default index"));
        }
        meta.functions.push_back(std::move(function));
    }

    if (reader.remaining() != 0) {
        throw MetadataError(
            "trailing bytes in PWBM metadata: "
            + std::to_string(reader.remaining()));
    }
    return meta;
}

void validate_meta(const Meta& meta, const Image& image) {
    if (meta.version != 1) {
        throw MetadataError("unsupported PWBM version");
    }
    for (std::size_t index = 0; index < meta.types.size(); ++index) {
        const MetaTypeSpec& type = meta.types[index];
        if (type.kind > MetaTypeKind::Param) {
            throw MetadataError("invalid PWBM type kind");
        }
        for (const std::uint32_t argument : type.args) {
            if (argument >= meta.types.size()) {
                throw MetadataError(
                    "PWBM type " + std::to_string(index)
                    + " argument index out of range");
            }
        }
        for (const std::uint32_t parameter : type.params) {
            if (parameter >= meta.types.size()) {
                throw MetadataError(
                    "PWBM type " + std::to_string(index)
                    + " parameter index out of range");
            }
        }
        if (type.returns != kAbsentIndex && type.returns >= meta.types.size()) {
            throw MetadataError(
                "PWBM type " + std::to_string(index)
                + " return index out of range");
        }
    }
    for (std::size_t index = 0; index < meta.functions.size(); ++index) {
        const FunctionMetadata& function = meta.functions[index];
        if (function.code_index >= image.codes.size()) {
            throw MetadataError(
                "PWBM function " + function.name
                + " code index out of range");
        }
        if (function.min_argc > function.parameters.size()) {
            throw MetadataError(
                "PWBM function " + function.name
                + " min argc exceeds its parameter count");
        }
        if (function.variadic_index < -1
            || (function.variadic_index >= 0
                && static_cast<std::size_t>(function.variadic_index)
                    >= function.parameters.size())) {
            throw MetadataError(
                "PWBM function " + function.name
                + " variadic index out of range");
        }
        for (const MetaParameter& parameter : function.parameters) {
            if (parameter.type_index >= meta.types.size()) {
                throw MetadataError(
                    "PWBM function " + function.name
                    + " parameter type index out of range");
            }
            if (parameter.default_index >= 0
                && static_cast<std::size_t>(parameter.default_index)
                    >= image.codes.size()) {
                throw MetadataError(
                    "PWBM function " + function.name
                    + " default code index out of range");
            }
        }
        for (const std::int32_t default_index : function.defaults) {
            if (default_index >= 0
                && static_cast<std::size_t>(default_index) >= image.codes.size()) {
                throw MetadataError(
                    "PWBM function " + function.name
                    + " default index out of range");
            }
        }
    }
}

std::string format_meta_summary(const Meta& meta) {
    std::ostringstream out;
    out << "meta version=" << meta.version
        << " functions=" << meta.functions.size()
        << " types=" << meta.types.size()
        << " hash=" << hex_hash(meta.image_hash) << "\n";
    for (std::size_t index = 0; index < meta.functions.size(); ++index) {
        const FunctionMetadata& function = meta.functions[index];
        out << "function " << index
            << " name=" << function.name
            << " code=" << function.code_index
            << " min=" << function.min_argc
            << " variadic="
            << (meta_flag(function, MetaFunctionFlag::Variadic) ? 1 : 0)
            << " variadic_index=" << function.variadic_index
            << " params=" << function.parameters.size() << "\n";
        for (std::size_t position = 0;
             position < function.parameters.size(); ++position) {
            const MetaParameter& parameter = function.parameters[position];
            out << "parameter " << position
                << " name=" << parameter.name
                << " type=" << parameter.type_index
                << " flags=" << static_cast<unsigned int>(parameter.flags)
                << " default=" << parameter.default_index << "\n";
        }
    }
    return out.str();
}

} // namespace pwb
