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
#include <vector>

#include "pwb/bigint.hpp"
#include "pwb/meta.hpp"
#include "pwb/value.hpp"

namespace pwb {

struct FunctionObject;

struct CapturedScope {
    std::unordered_map<std::string, Value> values;
    std::unordered_map<std::string, Value*> references;
    std::unordered_map<std::string, std::vector<FunctionObject*>> functions;
};

struct FunctionObject {
    const FunctionMetadata* metadata = nullptr;
    std::vector<Value> captures;
    CapturedScope captured;
    Value receiver = make_nova();
    bool has_receiver = false;
};

struct ArrayObject {
    std::vector<Value> items;
};

struct IteratorObject {
    std::vector<Value> values;
    std::size_t index = 0;
};

class Arena {
public:
    BigIntObject* allocate_bigint(BigInt value);
    ArrayObject* allocate_array(std::vector<Value> items = {});
    FunctionObject* allocate_function(const FunctionMetadata* metadata);
    IteratorObject* allocate_iterator(std::vector<Value> values);

    std::size_t bigint_count() const noexcept;
    std::size_t array_count() const noexcept;
    std::size_t function_count() const noexcept;
    std::size_t iterator_count() const noexcept;

private:
    std::deque<BigIntObject> bigints_;
    std::deque<ArrayObject> arrays_;
    std::deque<FunctionObject> functions_;
    std::deque<IteratorObject> iterators_;
};

} // namespace pwb
