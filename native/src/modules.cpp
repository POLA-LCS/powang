#include "pwb/module.hpp"

#include <algorithm>
#include <array>
#include <utility>

#include "pwb/error.hpp"
#include "pwb/sha256.hpp"

namespace pwb {

const BundleImport* ModuleRuntime::import_for(
    std::uint32_t image_module_index) const {
    if (bundle == nullptr) {
        return nullptr;
    }
    for (const BundleImport& binding : bundle->imports) {
        if (binding.image_module_index == image_module_index) {
            return &binding;
        }
    }
    return nullptr;
}

ModuleTable::ModuleTable(Bundle& bundle, Arena& arena) {
    (void)arena;
    entry_module_ = bundle.entry_module;
    const std::size_t count = bundle.modules.size();
    images_.resize(count);
    metas_.resize(count);
    modules_.resize(count);
    for (std::size_t index = 0; index < count; ++index) {
        BundleModule& record = bundle.modules[index];
        ModuleRuntime& module = modules_[index];
        module.module_id = record.module_id;
        module.bundle = &record;
        module.name = record.name;
        module.path = record.path;
        module.identity = record.identity;
        module.bind_project = record.bind_project;
        if (record.status != 0) {
            module.deferred_error_kind = record.error_kind;
            module.deferred_error_message = record.error_message;
            module.deferred_error_text = record.error_text;
            by_identity_[module.identity] = &module;
            continue;
        }
        images_[index] = parse_image(record.image.data(), record.image.size());
        metas_[index] = parse_meta(record.meta.data(), record.meta.size());
        validate_meta(metas_[index], images_[index]);
        const std::array<std::uint8_t, 32> expected =
            sha256(record.image.data(), record.image.size());
        if (!std::equal(
                expected.begin(), expected.end(),
                metas_[index].image_hash.begin())) {
            throw MetadataError(
                "module '" + record.name
                + "' metadata hash does not match its image");
        }
        module.image = &images_[index];
        module.meta = &metas_[index];
        by_identity_[module.identity] = &module;
    }
}

ModuleTable::ModuleTable(Image& image, const Meta* meta, std::string name) {
    entry_module_ = 0;
    modules_.resize(1);
    ModuleRuntime& module = modules_[0];
    module.module_id = 0;
    module.image = &image;
    module.meta = meta;
    module.name = std::move(name);
    module.path = module.name;
    module.identity = module.name;
    by_identity_[module.identity] = &module;
}

ModuleRuntime& ModuleTable::get(std::uint32_t module_id) {
    if (module_id >= modules_.size()) {
        throw RuntimeError("PWBB module id is out of range");
    }
    return modules_[module_id];
}

ModuleRuntime& ModuleTable::entry() {
    return get(entry_module_);
}

std::size_t ModuleTable::size() const noexcept {
    return modules_.size();
}

} // namespace pwb
