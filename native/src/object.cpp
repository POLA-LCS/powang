#include "pwb/object.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <string>
#include <utility>

namespace pwb {
namespace {

std::u32string decode_utf8(const std::string& text) {
    std::u32string out;
    std::size_t index = 0;
    while (index < text.size()) {
        const unsigned char first =
            static_cast<unsigned char>(text[index]);
        char32_t code_point = 0;
        std::size_t length = 0;
        if (first < 0x80u) {
            code_point = first;
            length = 1;
        } else if ((first & 0xE0u) == 0xC0u) {
            code_point = first & 0x1Fu;
            length = 2;
        } else if ((first & 0xF0u) == 0xE0u) {
            code_point = first & 0x0Fu;
            length = 3;
        } else if ((first & 0xF8u) == 0xF0u) {
            code_point = first & 0x07u;
            length = 4;
        } else {
            throw RuntimeError("invalid UTF-8 sequence");
        }
        if (index + length > text.size()) {
            throw RuntimeError("truncated UTF-8 sequence");
        }
        for (std::size_t offset = 1; offset < length; ++offset) {
            const unsigned char byte =
                static_cast<unsigned char>(text[index + offset]);
            if ((byte & 0xC0u) != 0x80u) {
                throw RuntimeError("invalid UTF-8 continuation byte");
            }
            code_point = (code_point << 6) | (byte & 0x3Fu);
        }
        if (!is_scalar_value(code_point)) {
            throw RuntimeError("UTF-8 sequence is not a Unicode scalar value");
        }
        out.push_back(code_point);
        index += length;
    }
    return out;
}

std::string encode_utf8(const std::u32string& text) {
    std::string out;
    for (const char32_t code_point : text) {
        if (!is_scalar_value(code_point)) {
            throw RuntimeError("string contains a non scalar code point");
        }
        append_utf8(out, code_point);
    }
    return out;
}

bool is_integer_like(const Value& value) {
    return value.tag == Tag::Bool || value.tag == Tag::Int
        || value.tag == Tag::BigInt;
}

BigInt to_bigint(const Value& value) {
    switch (value.tag) {
        case Tag::BigInt:
            return as_bigint_const(value)->value;
        case Tag::Int:
            return BigInt(value.i);
        case Tag::Bool:
            return BigInt(value.b ? 1 : 0);
        default:
            throw RuntimeError("expected an integer value");
    }
}

double as_number(const Value& value) {
    switch (value.tag) {
        case Tag::Bool:
            return value.b ? 1.0 : 0.0;
        case Tag::Int:
            return static_cast<double>(value.i);
        case Tag::BigInt:
            return as_bigint_const(value)->value.to_double();
        case Tag::Num:
            return value.d;
        default:
            return 0.0;
    }
}

std::string join_values(
    const std::vector<Value>& values, const std::string& separator) {
    std::string out;
    for (std::size_t index = 0; index < values.size(); ++index) {
        if (index != 0) {
            out += separator;
        }
        out += format_value(values[index]);
    }
    return out;
}

} // namespace

BigIntObject* Arena::allocate_bigint(BigInt value) {
    bigints_.push_back(BigIntObject{std::move(value)});
    return &bigints_.back();
}

ArrayObject* Arena::allocate_array(std::vector<Value> items) {
    arrays_.push_back(ArrayObject{std::move(items)});
    return &arrays_.back();
}

FunctionObject* Arena::allocate_function(const FunctionMetadata* metadata) {
    FunctionObject function;
    function.metadata = metadata;
    functions_.push_back(std::move(function));
    return &functions_.back();
}

IteratorObject* Arena::allocate_iterator(std::vector<Value> values) {
    IteratorObject iterator;
    iterator.values = std::move(values);
    iterators_.push_back(std::move(iterator));
    return &iterators_.back();
}

StringObject* Arena::allocate_string(std::u32string code_points) {
    StringObject object;
    object.code_points = std::move(code_points);
    object.utf8 = encode_utf8(object.code_points);
    strings_.push_back(std::move(object));
    return &strings_.back();
}

StringObject* Arena::allocate_string_utf8(const std::string& text) {
    return allocate_string(decode_utf8(text));
}

TupleObject* Arena::allocate_tuple(std::vector<Value> items) {
    tuples_.push_back(TupleObject{std::move(items)});
    return &tuples_.back();
}

MapObject* Arena::allocate_map() {
    maps_.push_back(MapObject{});
    return &maps_.back();
}

SetObject* Arena::allocate_set() {
    sets_.push_back(SetObject{});
    return &sets_.back();
}

ObjectObject* Arena::allocate_object(
    std::string type_name, bool is_enum, std::string variant) {
    ObjectObject object;
    object.type_name = std::move(type_name);
    object.is_enum = is_enum;
    object.variant = std::move(variant);
    objects_.push_back(std::move(object));
    return &objects_.back();
}

std::size_t Arena::bigint_count() const noexcept {
    return bigints_.size();
}

std::size_t Arena::array_count() const noexcept {
    return arrays_.size();
}

std::size_t Arena::function_count() const noexcept {
    return functions_.size();
}

std::size_t Arena::iterator_count() const noexcept {
    return iterators_.size();
}

std::size_t Arena::string_count() const noexcept {
    return strings_.size();
}

std::size_t Arena::tuple_count() const noexcept {
    return tuples_.size();
}

std::size_t Arena::map_count() const noexcept {
    return maps_.size();
}

std::size_t Arena::set_count() const noexcept {
    return sets_.size();
}

std::size_t Arena::object_count() const noexcept {
    return objects_.size();
}

std::string format_heap_value(const Value& value) {
    switch (value.tag) {
        case Tag::Str: {
            const StringObject* object = as_string_const(value);
            if (object == nullptr) {
                throw RuntimeError("null string value");
            }
            return object->utf8;
        }
        case Tag::Arr:
            return "[" + join_values(as_array(value)->items, ", ") + "]";
        case Tag::Tup:
            return "[" + join_values(as_tuple(value)->items, ", ") + "]";
        case Tag::Map: {
            std::string out = "[";
            const MapObject* map = as_map(value);
            for (std::size_t index = 0; index < map->entries.size(); ++index) {
                if (index != 0) {
                    out += ", ";
                }
                out += format_value(map->entries[index].first);
                out += " >> ";
                out += format_value(map->entries[index].second);
            }
            out += "]";
            return out;
        }
        case Tag::Set:
            return "[/" + join_values(as_set(value)->items, ", ") + "]";
        case Tag::Obj: {
            const ObjectObject* object = as_object(value);
            if (object->is_enum) {
                return "<" + object->type_name + ": "
                    + object->variant + ">";
            }
            return "<" + object->type_name + ">";
        }
        case Tag::Type: {
            const TypeRuntime* runtime = as_type(value);
            const std::string name =
                runtime != nullptr && runtime->info != nullptr
                ? runtime->info->name
                : "type";
            return "<" + name + ">";
        }
        default:
            throw RuntimeError("value has no heap formatting rule");
    }
}

bool heap_truthy(const Value& value) {
    switch (value.tag) {
        case Tag::Str:
            return !as_string_const(value)->code_points.empty();
        case Tag::Arr:
            return !as_array(value)->items.empty();
        case Tag::Tup:
            return !as_tuple(value)->items.empty();
        case Tag::Map:
            return !as_map(value)->entries.empty();
        case Tag::Set:
            return !as_set(value)->items.empty();
        case Tag::Obj:
        case Tag::Type:
            return true;
        default:
            return false;
    }
}

bool value_equal(const Value& left, const Value& right) {
    if (is_integer_like(left) && is_integer_like(right)) {
        return to_bigint(left).compare(to_bigint(right)) == 0;
    }
    if (left.tag == Tag::Num && is_integer_like(right)) {
        return left.d == as_number(right);
    }
    if (is_integer_like(left) && right.tag == Tag::Num) {
        return as_number(left) == right.d;
    }
    if (left.tag != right.tag) {
        if (left.tag == Tag::Str && right.tag == Tag::Char) {
            const StringObject* text = as_string_const(left);
            return text->code_points.size() == 1
                && text->code_points[0] == right.c;
        }
        if (left.tag == Tag::Char && right.tag == Tag::Str) {
            const StringObject* text = as_string_const(right);
            return text->code_points.size() == 1
                && text->code_points[0] == left.c;
        }
        return false;
    }
    switch (left.tag) {
        case Tag::Nova:
        case Tag::Undef:
            return true;
        case Tag::Bool:
            return left.b == right.b;
        case Tag::Int:
            return left.i == right.i;
        case Tag::Num:
            return left.d == right.d;
        case Tag::Char:
            return left.c == right.c;
        case Tag::BigInt:
            return as_bigint_const(left)->value.compare(
                       as_bigint_const(right)->value) == 0;
        case Tag::Str:
            return as_string_const(left)->code_points
                == as_string_const(right)->code_points;
        case Tag::Arr: {
            const ArrayObject* a = as_array(left);
            const ArrayObject* b = as_array(right);
            if (a->items.size() != b->items.size()) {
                return false;
            }
            for (std::size_t index = 0; index < a->items.size(); ++index) {
                if (!value_equal(a->items[index], b->items[index])) {
                    return false;
                }
            }
            return true;
        }
        case Tag::Tup: {
            const TupleObject* a = as_tuple(left);
            const TupleObject* b = as_tuple(right);
            if (a->items.size() != b->items.size()) {
                return false;
            }
            for (std::size_t index = 0; index < a->items.size(); ++index) {
                if (!value_equal(a->items[index], b->items[index])) {
                    return false;
                }
            }
            return true;
        }
        case Tag::Map: {
            const MapObject* a = as_map(left);
            const MapObject* b = as_map(right);
            if (a->entries.size() != b->entries.size()) {
                return false;
            }
            for (const auto& entry : a->entries) {
                const Value* found = map_get(*b, entry.first);
                if (found == nullptr || !value_equal(entry.second, *found)) {
                    return false;
                }
            }
            return true;
        }
        case Tag::Set: {
            const SetObject* a = as_set(left);
            const SetObject* b = as_set(right);
            if (a->items.size() != b->items.size()) {
                return false;
            }
            for (const Value& item : a->items) {
                if (!set_has(*b, item)) {
                    return false;
                }
            }
            return true;
        }
        case Tag::Obj: {
            const ObjectObject* a = as_object(left);
            const ObjectObject* b = as_object(right);
            if (a->is_enum && b->is_enum) {
                return a->type_name == b->type_name
                    && a->variant == b->variant;
            }
            return left.ref == right.ref;
        }
        case Tag::Type:
        case Tag::Fun:
        case Tag::Spread:
        case Tag::Iter:
            return left.ref == right.ref;
    }
    return false;
}

void map_set(MapObject& map, const Value& key, const Value& value) {
    for (auto& entry : map.entries) {
        if (value_equal(entry.first, key)) {
            entry.second = value;
            return;
        }
    }
    map.entries.emplace_back(key, value);
}

const Value* map_get(const MapObject& map, const Value& key) {
    for (const auto& entry : map.entries) {
        if (value_equal(entry.first, key)) {
            return &entry.second;
        }
    }
    return nullptr;
}

void set_add(SetObject& set, const Value& value) {
    if (!set_has(set, value)) {
        set.items.push_back(value);
    }
}

bool set_has(const SetObject& set, const Value& value) {
    for (const Value& item : set.items) {
        if (value_equal(item, value)) {
            return true;
        }
    }
    return false;
}

Value copy_value(Arena& arena, const Value& value, CopyMemo& memo) {
    switch (value.tag) {
        case Tag::Arr: {
            const auto found = memo.seen.find(value.ref);
            if (found != memo.seen.end()) {
                return found->second;
            }
            ArrayObject* copy = arena.allocate_array();
            const Value result = make_array(copy);
            memo.seen[value.ref] = result;
            const ArrayObject* source = as_array(value);
            copy->items.reserve(source->items.size());
            for (const Value& item : source->items) {
                copy->items.push_back(copy_value(arena, item, memo));
            }
            return result;
        }
        case Tag::Tup: {
            const auto found = memo.seen.find(value.ref);
            if (found != memo.seen.end()) {
                return found->second;
            }
            TupleObject* copy = arena.allocate_tuple();
            const Value result = make_tuple(copy);
            memo.seen[value.ref] = result;
            const TupleObject* source = as_tuple(value);
            copy->items.reserve(source->items.size());
            for (const Value& item : source->items) {
                copy->items.push_back(copy_value(arena, item, memo));
            }
            return result;
        }
        case Tag::Map: {
            const auto found = memo.seen.find(value.ref);
            if (found != memo.seen.end()) {
                return found->second;
            }
            MapObject* copy = arena.allocate_map();
            const Value result = make_map(copy);
            memo.seen[value.ref] = result;
            for (const auto& entry : as_map(value)->entries) {
                map_set(
                    *copy,
                    copy_value(arena, entry.first, memo),
                    copy_value(arena, entry.second, memo));
            }
            return result;
        }
        case Tag::Set: {
            const auto found = memo.seen.find(value.ref);
            if (found != memo.seen.end()) {
                return found->second;
            }
            SetObject* copy = arena.allocate_set();
            const Value result = make_set(copy);
            memo.seen[value.ref] = result;
            for (const Value& item : as_set(value)->items) {
                set_add(*copy, copy_value(arena, item, memo));
            }
            return result;
        }
        case Tag::Obj: {
            const auto found = memo.seen.find(value.ref);
            if (found != memo.seen.end()) {
                return found->second;
            }
            const ObjectObject* source = as_object(value);
            ObjectObject* copy = arena.allocate_object(
                source->type_name, source->is_enum, source->variant);
            copy->structure_locked = source->structure_locked;
            copy->elements_locked = source->elements_locked;
            copy->private_fields = source->private_fields;
            const Value result = make_object(copy);
            memo.seen[value.ref] = result;
            for (const auto& entry : source->fields) {
                copy->fields.emplace(
                    entry.first,
                    copy_value(arena, entry.second, memo));
            }
            return result;
        }
        case Tag::Type:
        case Tag::Str:
        case Tag::BigInt:
        case Tag::Fun:
        case Tag::Nova:
        case Tag::Undef:
        case Tag::Bool:
        case Tag::Int:
        case Tag::Num:
        case Tag::Char:
        case Tag::Spread:
        case Tag::Iter:
            return value;
    }
    return value;
}

Value copy_value(Arena& arena, const Value& value) {
    CopyMemo memo;
    return copy_value(arena, value, memo);
}

} // namespace pwb
