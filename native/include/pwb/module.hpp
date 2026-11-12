// Per-module runtime state for the native bundle path.
//
// One ModuleRuntime exists per PWBB module record. It owns the symbol tables
// and the cache state. The image and metadata stay in the bundle record (or in
// the ModuleTable's parsed storage), never in the runtime.

#pragma once

#include <cstdint>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

#include "pwb/bundle.hpp"
#include "pwb/image.hpp"
#include "pwb/meta.hpp"
#include "pwb/object.hpp"
#include "pwb/value.hpp"

namespace pwb {

struct ModuleRuntime;

struct TraitRuntime {
    const TraitInfo* info = nullptr;
    ModuleRuntime* module = nullptr;
    std::unordered_map<std::string, std::vector<FunctionObject*>> defaults;
};

struct ExportEntry {
    enum class Kind : std::uint8_t { Variable, Function, Type };

    Kind kind = Kind::Variable;
    Value value = make_nova();
    std::vector<FunctionObject*> functions;
    TypeRuntime* type = nullptr;
};

struct ModuleRuntime {
    enum class Init : std::uint8_t { New, Initializing, Ready, Failed };

    const BundleModule* bundle = nullptr;
    const Image* image = nullptr;
    const Meta* meta = nullptr;
    std::string name;
    std::string path;
    std::string identity;
    std::uint32_t module_id = 0;
    bool bind_project = false;
    bool legacy = false;
    bool warned = false;
    Init init = Init::New;

    std::string deferred_error_kind;
    std::string deferred_error_message;
    std::string deferred_error_text;

    std::unordered_map<std::string, Value> globals;
    std::unordered_set<std::string> declared_globals;
    std::unordered_map<std::string, std::vector<FunctionObject*>> functions;
    std::unordered_map<std::string, TypeRuntime> types;
    std::unordered_map<std::string, TraitRuntime> traits;
    std::unordered_map<std::string, ModuleRuntime*> aliases;

    std::unordered_map<std::string, Value> wildcard_values;
    std::unordered_map<std::string, std::vector<FunctionObject*>> wildcard_functions;
    std::unordered_map<std::string, TypeRuntime*> wildcard_types;
    std::unordered_map<std::string, std::string> wildcard_sources;

    std::unordered_map<std::string, ExportEntry> exports;

    const BundleImport* import_for(std::uint32_t image_module_index) const;
};

class ModuleTable {
public:
    ModuleTable() = default;
    ModuleTable(Bundle& bundle, Arena& arena);
    ModuleTable(Image& image, const Meta* meta, std::string name);

    ModuleRuntime& get(std::uint32_t module_id);
    ModuleRuntime& entry();
    std::size_t size() const noexcept;

private:
    std::uint32_t entry_module_ = 0;
    std::vector<Image> images_;
    std::vector<Meta> metas_;
    std::vector<ModuleRuntime> modules_;
    std::unordered_map<std::string, ModuleRuntime*> by_identity_;
};

} // namespace pwb
