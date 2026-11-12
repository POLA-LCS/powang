#include "pwb/object.hpp"

#include <utility>

namespace pwb {

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

} // namespace pwb
