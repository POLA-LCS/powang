// Heap objects and the N1 arena for the native runtime.
//
// N1 needs function values, variadic arrays and arbitrary precision integers.
// Full reference counting and copy-on-write arrive at N2. The N1 arena owns
// objects until the program ends and hands out stable addresses.

#pragma once

#include <cstddef>
#include <deque>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

#include "pwb/bigint.hpp"
#include "pwb/errors.hpp"
#include "pwb/file.hpp"
#include "pwb/image.hpp"
#include "pwb/meta.hpp"
#include "pwb/references.hpp"
#include "pwb/task.hpp"
#include "pwb/value.hpp"

namespace pwb {

struct FunctionObject;
struct TypeRuntime;
struct ModuleRuntime;
struct ErrorObject;
struct ProjectObject;

struct CapturedScope {
    std::unordered_map<std::string, Value> values;
    std::unordered_map<std::string, Value*> references;
    std::unordered_map<std::string, std::vector<FunctionObject*>> functions;
};

struct FunctionObject {
    const FunctionMetadata* metadata = nullptr;
    ModuleRuntime* module = nullptr;
    const MetaDescriptor* extern_descriptor = nullptr;
    std::vector<Value> captures;
    CapturedScope captured;
    Value receiver = make_nova();
    bool has_receiver = false;
    TypeRuntime* owner = nullptr;
    bool is_static = false;
    bool is_private = false;
    std::string trait_qualifier;
};

struct ObjectObject {
    TypeRuntime* type = nullptr;
    ModuleRuntime* module = nullptr;
    std::string type_name;
    std::string variant;
    bool is_enum = false;
    bool structure_locked = false;
    bool elements_locked = false;
    std::unordered_map<std::string, Value> fields;
    std::unordered_set<std::string> private_fields;
};

struct TypeRuntime {
    const TypeInfo* info = nullptr;
    ModuleRuntime* module = nullptr;
    std::string qualified_name;
    std::unordered_map<std::string, std::vector<FunctionObject*>> methods;
    std::unordered_map<std::string, std::vector<FunctionObject*>> statics;
    std::unordered_map<std::string, std::vector<FunctionObject*>> constructors;
    std::unordered_map<
        std::string,
        std::unordered_map<std::string, std::vector<FunctionObject*>>>
        trait_methods;
};

struct ArrayObject {
    std::vector<Value> items;
    bool structure_locked = false;
    bool elements_locked = false;
};

struct StringObject {
    std::u32string code_points;
    std::string utf8;
};

struct TupleObject {
    std::vector<Value> items;
};

struct MapObject {
    std::vector<std::pair<Value, Value>> entries;
    bool structure_locked = false;
    bool elements_locked = false;
};

struct SetObject {
    std::vector<Value> items;
    bool structure_locked = false;
    bool elements_locked = false;
};

struct IteratorObject {
    std::vector<Value> values;
    std::size_t index = 0;
};

struct CopyMemo {
    std::unordered_map<const void*, Value> seen;
};

class Arena {
public:
    BigIntObject* allocate_bigint(BigInt value);
    ArrayObject* allocate_array(std::vector<Value> items = {});
    FunctionObject* allocate_function(const FunctionMetadata* metadata);
    IteratorObject* allocate_iterator(std::vector<Value> values);
    StringObject* allocate_string(std::u32string code_points);
    StringObject* allocate_string_utf8(const std::string& text);
    TupleObject* allocate_tuple(std::vector<Value> items = {});
    MapObject* allocate_map();
    SetObject* allocate_set();
    ObjectObject* allocate_object(
        std::string type_name,
        bool is_enum = false,
        std::string variant = "");
    ErrorObject* allocate_error();
    RefObject* allocate_reference();
    TaskObject* allocate_task();
    FileObject* allocate_file(std::string path, std::string mode);

    std::size_t bigint_count() const noexcept;
    std::size_t array_count() const noexcept;
    std::size_t function_count() const noexcept;
    std::size_t iterator_count() const noexcept;
    std::size_t string_count() const noexcept;
    std::size_t tuple_count() const noexcept;
    std::size_t map_count() const noexcept;
    std::size_t set_count() const noexcept;
    std::size_t object_count() const noexcept;
    std::size_t error_count() const noexcept;

private:
    std::deque<BigIntObject> bigints_;
    std::deque<ArrayObject> arrays_;
    std::deque<FunctionObject> functions_;
    std::deque<IteratorObject> iterators_;
    std::deque<StringObject> strings_;
    std::deque<TupleObject> tuples_;
    std::deque<MapObject> maps_;
    std::deque<SetObject> sets_;
    std::deque<ObjectObject> objects_;
    std::deque<ErrorObject> errors_;
    std::deque<RefObject> references_;
    std::deque<TaskObject> tasks_;
    std::deque<FileObject> files_;
};

std::string format_heap_value(const Value& value);
bool heap_truthy(const Value& value);
bool value_equal(const Value& left, const Value& right);
Value copy_value(Arena& arena, const Value& value, CopyMemo& memo);
Value copy_value(Arena& arena, const Value& value);
void map_set(MapObject& map, const Value& key, const Value& value);
const Value* map_get(const MapObject& map, const Value& key);
void set_add(SetObject& set, const Value& value);
bool set_has(const SetObject& set, const Value& value);

} // namespace pwb
