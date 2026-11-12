// PWBB bundle container for the native runtime.
//
// A bundle carries the entry PWB1 image, its PWBM metadata and every reachable
// imported module image. The raw single-image path stays available.

#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <utility>
#include <vector>

namespace pwb {

struct BundleImport {
    std::uint32_t image_module_index = 0;
    std::uint32_t target_module_id = 0;
    std::string alias;
    bool wildcard = false;
    bool explicit_alias = false;
};

struct BundleModule {
    std::uint32_t module_id = 0;
    std::uint32_t image_module_index = 0;
    std::uint8_t status = 0;
    bool bind_project = false;
    std::string name;
    std::string path;
    std::string identity;
    std::vector<std::uint8_t> image;
    std::vector<std::uint8_t> meta;
    std::vector<BundleImport> imports;
    std::vector<std::pair<std::string, std::uint8_t>> exports;
    std::string error_kind;
    std::string error_message;
    std::string error_text;
};

struct BundleProject {
    std::vector<std::string> modules;
    std::vector<std::string> paths;
    std::string log_level;
    bool allow_system = false;
    std::string engine;
};

struct Bundle {
    std::uint16_t version = 0;
    std::uint16_t flags = 0;
    std::uint32_t entry_module = 0;
    std::string entry_path;
    std::uint32_t entry_source_line_count = 0;
    std::vector<BundleModule> modules;
    bool has_project = false;
    BundleProject project;
    std::array<std::uint8_t, 32> digest{};
};

Bundle parse_bundle(const std::uint8_t* data, std::size_t size);
std::string format_bundle_summary(const Bundle& bundle);

} // namespace pwb
