#include "pwb/bundle.hpp"

#include <algorithm>
#include <cstring>
#include <iomanip>
#include <sstream>
#include <string>

#include "pwb/error.hpp"
#include "pwb/image.hpp"
#include "pwb/meta.hpp"
#include "pwb/sha256.hpp"
#include "pwb/verifier.hpp"

namespace pwb {
namespace {

constexpr std::uint16_t kBundleVersion = 1;
constexpr std::uint16_t kBundleFlagProject = 1 << 0;

class BundleReader {
public:
    BundleReader(const std::uint8_t* data, std::size_t size)
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

    std::string string(const char* what) {
        const std::uint32_t length = u32(what);
        const std::uint8_t* bytes = take(length, what);
        return std::string(
            reinterpret_cast<const char*>(bytes),
            static_cast<std::size_t>(length));
    }

    std::vector<std::uint8_t> bytes(const char* what) {
        const std::uint32_t length = u32(what);
        const std::uint8_t* data = take(length, what);
        return std::vector<std::uint8_t>(data, data + length);
    }

    std::size_t remaining() const {
        return size_ - offset_;
    }

    const std::uint8_t* take(std::size_t count, const char* what) {
        if (count > size_ - offset_) {
            throw BundleError(
                std::string("truncated PWBB bundle while reading ")
                + what + " at offset " + std::to_string(offset_));
        }
        const std::uint8_t* result = data_ + offset_;
        offset_ += count;
        return result;
    }

private:
    const std::uint8_t* data_;
    std::size_t size_;
    std::size_t offset_ = 0;
};

std::string hex_digest(const std::array<std::uint8_t, 32>& digest) {
    std::ostringstream out;
    out << std::hex << std::setfill('0');
    for (const std::uint8_t byte : digest) {
        out << std::setw(2) << static_cast<unsigned int>(byte);
    }
    return out.str();
}

void validate_embedded_module(
    const std::vector<std::uint8_t>& image_bytes,
    const std::vector<std::uint8_t>& meta_bytes,
    const std::string& name) {
    const Image image = parse_image(image_bytes.data(), image_bytes.size());
    const Meta meta = parse_meta(meta_bytes.data(), meta_bytes.size());
    validate_meta(meta, image);
    const std::array<std::uint8_t, 32> expected =
        sha256(image_bytes.data(), image_bytes.size());
    if (!std::equal(
            expected.begin(), expected.end(), meta.image_hash.begin())) {
        throw MetadataError(
            "module '" + name + "' metadata hash does not match its image");
    }
}

} // namespace

Bundle parse_bundle(const std::uint8_t* data, std::size_t size) {
    if (size < 32) {
        throw BundleError("PWBB bundle is shorter than its digest");
    }
    const std::size_t payload_size = size - 32;
    const std::array<std::uint8_t, 32> computed =
        sha256(data, payload_size);
    if (!std::equal(
            computed.begin(), computed.end(), data + payload_size)) {
        throw BundleError("PWBB bundle digest mismatch");
    }
    BundleReader reader(data, payload_size);
    const std::uint8_t* magic = reader.take(4, "magic");
    if (magic[0] != 'P' || magic[1] != 'W' || magic[2] != 'B'
        || magic[3] != 'B') {
        throw BundleError("invalid PWBB magic");
    }
    Bundle bundle;
    bundle.version = reader.u16("version");
    if (bundle.version != kBundleVersion) {
        throw BundleError(
            "unsupported PWBB version: "
            + std::to_string(bundle.version));
    }
    bundle.flags = reader.u16("flags");
    bundle.entry_module = reader.u32("entry module");
    const std::uint32_t module_count = reader.u32("module count");
    if (module_count > 100000u) {
        throw BundleError("PWBB module count is too large");
    }
    bundle.entry_path = reader.string("entry path");
    bundle.entry_source_line_count =
        reader.u32("entry source line count");
    if ((bundle.flags & kBundleFlagProject) != 0) {
        bundle.has_project = true;
        const std::uint32_t project_module_count =
            reader.u32("project module count");
        for (std::uint32_t index = 0; index < project_module_count; ++index) {
            bundle.project.modules.push_back(
                reader.string("project module"));
        }
        const std::uint32_t project_path_count =
            reader.u32("project path count");
        for (std::uint32_t index = 0; index < project_path_count; ++index) {
            bundle.project.paths.push_back(reader.string("project path"));
        }
        bundle.project.log_level = reader.string("project log level");
        bundle.project.allow_system =
            reader.u8("project allow system") != 0;
        const std::uint8_t* reserved = reader.take(3, "project reserved");
        (void)reserved;
        bundle.project.engine = reader.string("project engine");
    }
    bundle.modules.reserve(module_count);
    for (std::uint32_t index = 0; index < module_count; ++index) {
        BundleModule module;
        module.module_id = reader.u32("module id");
        if (module.module_id != index) {
            throw BundleError(
                "PWBB module id does not equal its index");
        }
        module.image_module_index = reader.u32("module image index");
        module.status = reader.u8("module status");
        module.bind_project = reader.u8("module bind project") != 0;
        const std::uint8_t* reserved = reader.take(2, "module reserved");
        (void)reserved;
        module.name = reader.string("module name");
        module.path = reader.string("module path");
        module.identity = reader.string("module identity");
        if (module.status == 0) {
            module.image = reader.bytes("module image");
            module.meta = reader.bytes("module metadata");
            validate_embedded_module(module.image, module.meta, module.name);
            const std::uint32_t import_count =
                reader.u32("module import count");
            module.imports.reserve(import_count);
            for (std::uint32_t position = 0; position < import_count;
                 ++position) {
                BundleImport item;
                item.image_module_index =
                    reader.u32("import image module index");
                item.target_module_id =
                    reader.u32("import target module id");
                const std::uint8_t flags = reader.u8("import flags");
                const std::uint8_t* import_reserved =
                    reader.take(3, "import reserved");
                (void)import_reserved;
                item.wildcard = (flags & 1) != 0;
                item.explicit_alias = (flags & 2) != 0;
                item.alias = reader.string("import alias");
                module.imports.push_back(std::move(item));
            }
            const std::uint32_t export_count =
                reader.u32("module export count");
            module.exports.reserve(export_count);
            for (std::uint32_t position = 0; position < export_count;
                 ++position) {
                const std::string name = reader.string("export name");
                const std::uint8_t kind = reader.u8("export kind");
                if (kind > 2) {
                    throw BundleError("unknown PWBB export kind");
                }
                module.exports.emplace_back(name, kind);
            }
        } else {
            module.error_kind = reader.string("module error kind");
            module.error_message = reader.string("module error message");
            module.error_text = reader.string("module error text");
        }
        bundle.modules.push_back(std::move(module));
    }
    if (reader.remaining() != 0) {
        throw BundleError(
            "trailing bytes in PWBB bundle: "
            + std::to_string(reader.remaining()));
    }
    if (bundle.entry_module >= bundle.modules.size()) {
        throw BundleError("PWBB entry module is out of range");
    }
    std::copy(
        data + payload_size, data + size, bundle.digest.begin());
    return bundle;
}

std::string format_bundle_summary(const Bundle& bundle) {
    std::ostringstream out;
    out << "bundle version=" << bundle.version
        << " entry=" << bundle.entry_module
        << " modules=" << bundle.modules.size()
        << " digest=" << hex_digest(bundle.digest) << "\n";
    for (const BundleModule& module : bundle.modules) {
        out << "module " << module.module_id
            << " name=" << module.name
            << " path=" << module.path
            << " identity=" << module.identity
            << " status=" << static_cast<unsigned int>(module.status)
            << " image=" << module.image.size()
            << " meta=" << module.meta.size()
            << " imports=" << module.imports.size()
            << " exports=" << module.exports.size() << "\n";
    }
    return out.str();
}

} // namespace pwb
