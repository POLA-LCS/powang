// Reference values for the native runtime.
//
// A reference is an immutable identity value that points at live storage. The
// storage kinds are local slots, module globals, object fields and array
// elements. Frame lifetime is tracked with a shared token so a stale local
// reference is rejected instead of dereferenced.

#pragma once

#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>

#include "pwb/value.hpp"

namespace pwb {

struct ModuleRuntime;
struct ObjectObject;
struct ArrayObject;

struct FrameLifetime {
    bool alive = true;
    std::uint64_t generation = 0;
};

struct RefObject {
    enum class Kind : std::uint8_t { Local, Global, Field, Index };

    Kind kind = Kind::Local;
    void* frame = nullptr;
    std::shared_ptr<FrameLifetime> lifetime;
    std::uint64_t generation = 0;
    std::uint32_t slot = 0;
    ModuleRuntime* module = nullptr;
    std::string name;
    ObjectObject* object = nullptr;
    ArrayObject* array = nullptr;
    std::size_t index = 0;
    std::string target_type;
    bool defined = true;
    bool is_const = false;
};

} // namespace pwb
