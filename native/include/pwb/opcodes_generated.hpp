// Generated from src/vm/opcodes.py by src/vm/native/gen_opcodes.py.
// Do not edit by hand.
#pragma once

#include <cstddef>
#include <cstdint>

#include "pwb/opcodes.hpp"

namespace pwb {

enum class Opcode : std::uint8_t {
    NOP = 0,
    POP = 1,
    DUP = 2,
    DUP2 = 3,
    SWAP = 4,
    ROT3 = 5,
    ROT = 6,
    LOAD_NOVA = 7,
    LOAD_UNDEF = 8,
    LOAD_TRUE = 9,
    LOAD_FALSE = 10,
    LOAD_INT = 11,
    LOAD_BIGINT = 12,
    LOAD_NUM = 13,
    LOAD_CHAR = 14,
    LOAD_STR = 15,
    LOAD_CONST = 16,
    DECLARE_LOCAL = 17,
    DECLARE_GLOBAL = 18,
    DECLARE_TYPED = 19,
    DECLARE_INFER = 20,
    DECLARE_TYPED_GLOBAL = 21,
    DECLARE_INFER_GLOBAL = 22,
    DECLARE_UNDEFINED_GLOBAL = 23,
    DESTRUCTURE = 24,
    DECLARE_FUNCTION = 25,
    DECLARE_TYPE = 26,
    DECLARE_TRAIT = 27,
    DECLARE_EXTERN = 28,
    LOAD_LOCAL = 29,
    STORE_LOCAL = 30,
    LOAD_GLOBAL = 31,
    STORE_GLOBAL = 32,
    LOAD_NAME = 33,
    STORE_NAME = 34,
    LOAD_CAPTURE = 35,
    MAKE_CAPTURE = 36,
    LOAD_THIS = 37,
    COPY = 38,
    CAST_ASSIGN = 39,
    CAST_RETURN = 40,
    BOX_ANY = 41,
    UNBOX_ANY = 42,
    MAKE_ARRAY = 43,
    MAKE_ARRAY_TYPED = 44,
    MAKE_TUPLE = 45,
    MAKE_TUPLE_TYPED = 46,
    MAKE_MAP = 47,
    MAKE_MAP_TYPED = 48,
    MAKE_SET = 49,
    MAKE_SET_TYPED = 50,
    MAKE_EMPTY_MAP = 51,
    MAKE_EMPTY_SET = 52,
    INDEX_GET = 53,
    INDEX_SET = 54,
    SLICE = 55,
    SIZE = 56,
    ITER_NEW = 57,
    ITER_NEXT = 58,
    ADD = 59,
    SUB = 60,
    MUL = 61,
    DIV = 62,
    MOD = 63,
    NEG = 64,
    NOT = 65,
    EQ = 66,
    NEQ = 67,
    LT = 68,
    LE = 69,
    GT = 70,
    GE = 71,
    EQ_TYPED = 72,
    NEQ_TYPED = 73,
    LT_TYPED = 74,
    LE_TYPED = 75,
    GT_TYPED = 76,
    GE_TYPED = 77,
    CONCAT_STR = 78,
    TO_STRING = 79,
    TO_BOOL = 80,
    REVERSE = 81,
    CAST = 82,
    TYPE_CHECK = 83,
    TYPE_CHECK_NOT = 84,
    TYPE_CHECK_VALUE = 85,
    IS_NOVA = 86,
    IS_DEFINED = 87,
    IS_WEAK = 88,
    JUMP = 89,
    JUMP_IF_FALSE = 90,
    JUMP_IF_TRUE = 91,
    JUMP_IF_FALSE_KEEP = 92,
    JUMP_IF_TRUE_KEEP = 93,
    JUMP_IF_NOVA = 94,
    JUMP_IF_NOT_NOVA = 95,
    MATCH = 96,
    RETURN = 97,
    CHECK_CANCEL = 98,
    CALL = 99,
    CALL_VALUE = 100,
    CALL_METHOD = 101,
    CALL_STATIC = 102,
    CALL_MODULE = 103,
    CALL_NATIVE = 104,
    CALL_BUILTIN = 105,
    CALL_TRAIT = 106,
    CALL_OPERATOR = 107,
    CALL_EXTERN = 108,
    CALL_ASYNC = 109,
    CALL_ASYNC_METHOD = 110,
    SPAWN = 111,
    AWAIT = 112,
    CONSTRUCT = 113,
    NEW_ENUM = 114,
    LOAD_FIELD = 115,
    STORE_FIELD = 116,
    LOAD_MEMBER = 117,
    STORE_MEMBER = 118,
    LOAD_MEMBER_SAFE = 119,
    LOAD_ENUM_MEMBER = 120,
    SET_LOCKS = 121,
    CHECK_TRAIT = 122,
    TRAIT_CAST = 123,
    MAKE_ERROR = 124,
    ERROR_PROPERTY = 125,
    THROW = 126,
    PROPAGATE = 127,
    TRY_BEGIN = 128,
    TRY_END = 129,
    FINALLY_END = 130,
    RETHROW = 131,
    REF_LOCAL = 132,
    REF_GLOBAL = 133,
    REF_FIELD = 134,
    REF_INDEX = 135,
    LOAD_REF = 136,
    STORE_REF = 137,
    IMPORT = 138,
    IMPORT_WILDCARD = 139,
    LOAD_MODULE_MEMBER = 140,
    LOAD_PROJECT = 141,
    EXPORT = 142,
    TRACE_EVENT = 143,
    HOST_CALL = 144,
    ASSIGN_LOCAL = 145,
    ASSIGN_NAME = 146,
    MAKE_FUNCTION = 147,
    MAKE_SPREAD = 148,
    LOAD_RAW = 149,
    STORE_RAW = 150,
    ADD_TYPED = 151,
    SUB_TYPED = 152,
    MUL_TYPED = 153,
    DIV_TYPED = 154,
    MOD_TYPED = 155,
    SET_RETURN = 156,
    SET_TRANSFER = 157,
    JUMP_IF_TRANSFER = 158,
    APPLY_TRANSFER = 159,
    ABANDON_FINALLY = 160,
    LOAD_FREE = 161,
    SCOPE_PUSH = 162,
    SCOPE_POP = 163,
};

namespace generated {

inline constexpr OperandSpec kOperands_ROT[] = {
    {"count", Width::U16, OperandKind::Value},
};

inline constexpr OperandSpec kOperands_LOAD_INT[] = {
    {"value", Width::I64, OperandKind::Value},
};

inline constexpr OperandSpec kOperands_LOAD_BIGINT[] = {
    {"const", Width::U32, OperandKind::Const},
};

inline constexpr OperandSpec kOperands_LOAD_NUM[] = {
    {"value", Width::F64, OperandKind::Value},
};

inline constexpr OperandSpec kOperands_LOAD_CHAR[] = {
    {"value", Width::U32, OperandKind::Value},
};

inline constexpr OperandSpec kOperands_LOAD_STR[] = {
    {"const", Width::U32, OperandKind::Const},
};

inline constexpr OperandSpec kOperands_LOAD_CONST[] = {
    {"const", Width::U32, OperandKind::Const},
};

inline constexpr OperandSpec kOperands_DECLARE_LOCAL[] = {
    {"slot", Width::U16, OperandKind::Slot},
    {"spec", Width::U32, OperandKind::Spec},
    {"flags", Width::U8, OperandKind::Flags},
};

inline constexpr OperandSpec kOperands_DECLARE_GLOBAL[] = {
    {"name", Width::U32, OperandKind::Name},
    {"spec", Width::U32, OperandKind::Spec},
    {"flags", Width::U8, OperandKind::Flags},
};

inline constexpr OperandSpec kOperands_DECLARE_TYPED[] = {
    {"slot", Width::U16, OperandKind::Slot},
    {"spec", Width::U32, OperandKind::Spec},
};

inline constexpr OperandSpec kOperands_DECLARE_INFER[] = {
    {"slot", Width::U16, OperandKind::Slot},
};

inline constexpr OperandSpec kOperands_DECLARE_TYPED_GLOBAL[] = {
    {"name", Width::U32, OperandKind::Name},
    {"spec", Width::U32, OperandKind::Spec},
};

inline constexpr OperandSpec kOperands_DECLARE_INFER_GLOBAL[] = {
    {"name", Width::U32, OperandKind::Name},
};

inline constexpr OperandSpec kOperands_DECLARE_UNDEFINED_GLOBAL[] = {
    {"name", Width::U32, OperandKind::Name},
    {"spec", Width::U32, OperandKind::Spec},
    {"flags", Width::U8, OperandKind::Flags},
};

inline constexpr OperandSpec kOperands_DESTRUCTURE[] = {
    {"descriptor", Width::U32, OperandKind::Const},
    {"source_slot", Width::U16, OperandKind::Slot},
};

inline constexpr OperandSpec kOperands_DECLARE_FUNCTION[] = {
    {"function", Width::U32, OperandKind::Value},
};

inline constexpr OperandSpec kOperands_DECLARE_TYPE[] = {
    {"type", Width::U32, OperandKind::Type},
};

inline constexpr OperandSpec kOperands_DECLARE_TRAIT[] = {
    {"trait", Width::U32, OperandKind::Trait},
};

inline constexpr OperandSpec kOperands_DECLARE_EXTERN[] = {
    {"extern", Width::U32, OperandKind::Value},
};

inline constexpr OperandSpec kOperands_LOAD_LOCAL[] = {
    {"slot", Width::U16, OperandKind::Slot},
};

inline constexpr OperandSpec kOperands_STORE_LOCAL[] = {
    {"slot", Width::U16, OperandKind::Slot},
};

inline constexpr OperandSpec kOperands_LOAD_GLOBAL[] = {
    {"name", Width::U32, OperandKind::Name},
};

inline constexpr OperandSpec kOperands_STORE_GLOBAL[] = {
    {"name", Width::U32, OperandKind::Name},
};

inline constexpr OperandSpec kOperands_LOAD_NAME[] = {
    {"name", Width::U32, OperandKind::Name},
};

inline constexpr OperandSpec kOperands_STORE_NAME[] = {
    {"name", Width::U32, OperandKind::Name},
};

inline constexpr OperandSpec kOperands_LOAD_CAPTURE[] = {
    {"index", Width::U16, OperandKind::Value},
};

inline constexpr OperandSpec kOperands_MAKE_CAPTURE[] = {
    {"slot", Width::U16, OperandKind::Slot},
};

inline constexpr OperandSpec kOperands_CAST_ASSIGN[] = {
    {"spec", Width::U32, OperandKind::Spec},
};

inline constexpr OperandSpec kOperands_CAST_RETURN[] = {
    {"spec", Width::U32, OperandKind::Spec},
};

inline constexpr OperandSpec kOperands_BOX_ANY[] = {
    {"spec", Width::U32, OperandKind::Spec},
};

inline constexpr OperandSpec kOperands_MAKE_ARRAY[] = {
    {"count", Width::U16, OperandKind::Value},
};

inline constexpr OperandSpec kOperands_MAKE_ARRAY_TYPED[] = {
    {"spec", Width::U32, OperandKind::Spec},
    {"count", Width::U16, OperandKind::Value},
};

inline constexpr OperandSpec kOperands_MAKE_TUPLE[] = {
    {"count", Width::U16, OperandKind::Value},
};

inline constexpr OperandSpec kOperands_MAKE_TUPLE_TYPED[] = {
    {"spec", Width::U32, OperandKind::Spec},
    {"count", Width::U16, OperandKind::Value},
};

inline constexpr OperandSpec kOperands_MAKE_MAP[] = {
    {"count", Width::U16, OperandKind::Value},
};

inline constexpr OperandSpec kOperands_MAKE_MAP_TYPED[] = {
    {"spec", Width::U32, OperandKind::Spec},
    {"count", Width::U16, OperandKind::Value},
};

inline constexpr OperandSpec kOperands_MAKE_SET[] = {
    {"count", Width::U16, OperandKind::Value},
};

inline constexpr OperandSpec kOperands_MAKE_SET_TYPED[] = {
    {"spec", Width::U32, OperandKind::Spec},
    {"count", Width::U16, OperandKind::Value},
};

inline constexpr OperandSpec kOperands_ITER_NEXT[] = {
    {"target", Width::I32, OperandKind::Target},
};

inline constexpr OperandSpec kOperands_CONCAT_STR[] = {
    {"count", Width::U16, OperandKind::Value},
};

inline constexpr OperandSpec kOperands_CAST[] = {
    {"spec", Width::U32, OperandKind::Spec},
};

inline constexpr OperandSpec kOperands_TYPE_CHECK[] = {
    {"spec", Width::U32, OperandKind::Spec},
};

inline constexpr OperandSpec kOperands_TYPE_CHECK_NOT[] = {
    {"spec", Width::U32, OperandKind::Spec},
};

inline constexpr OperandSpec kOperands_JUMP[] = {
    {"target", Width::I32, OperandKind::Target},
};

inline constexpr OperandSpec kOperands_JUMP_IF_FALSE[] = {
    {"target", Width::I32, OperandKind::Target},
};

inline constexpr OperandSpec kOperands_JUMP_IF_TRUE[] = {
    {"target", Width::I32, OperandKind::Target},
};

inline constexpr OperandSpec kOperands_JUMP_IF_FALSE_KEEP[] = {
    {"target", Width::I32, OperandKind::Target},
};

inline constexpr OperandSpec kOperands_JUMP_IF_TRUE_KEEP[] = {
    {"target", Width::I32, OperandKind::Target},
};

inline constexpr OperandSpec kOperands_JUMP_IF_NOVA[] = {
    {"target", Width::I32, OperandKind::Target},
};

inline constexpr OperandSpec kOperands_JUMP_IF_NOT_NOVA[] = {
    {"target", Width::I32, OperandKind::Target},
};

inline constexpr OperandSpec kOperands_MATCH[] = {
    {"pattern", Width::U32, OperandKind::Pattern},
    {"target", Width::I32, OperandKind::Target},
};

inline constexpr OperandSpec kOperands_CALL[] = {
    {"call", Width::U32, OperandKind::Call},
};

inline constexpr OperandSpec kOperands_CALL_VALUE[] = {
    {"call", Width::U32, OperandKind::Call},
};

inline constexpr OperandSpec kOperands_CALL_METHOD[] = {
    {"call", Width::U32, OperandKind::Call},
};

inline constexpr OperandSpec kOperands_CALL_STATIC[] = {
    {"call", Width::U32, OperandKind::Call},
};

inline constexpr OperandSpec kOperands_CALL_MODULE[] = {
    {"call", Width::U32, OperandKind::Call},
};

inline constexpr OperandSpec kOperands_CALL_NATIVE[] = {
    {"call", Width::U32, OperandKind::Call},
};

inline constexpr OperandSpec kOperands_CALL_BUILTIN[] = {
    {"call", Width::U32, OperandKind::Call},
};

inline constexpr OperandSpec kOperands_CALL_TRAIT[] = {
    {"call", Width::U32, OperandKind::Call},
};

inline constexpr OperandSpec kOperands_CALL_OPERATOR[] = {
    {"call", Width::U32, OperandKind::Call},
};

inline constexpr OperandSpec kOperands_CALL_EXTERN[] = {
    {"call", Width::U32, OperandKind::Call},
};

inline constexpr OperandSpec kOperands_CALL_ASYNC[] = {
    {"call", Width::U32, OperandKind::Call},
};

inline constexpr OperandSpec kOperands_CALL_ASYNC_METHOD[] = {
    {"call", Width::U32, OperandKind::Call},
};

inline constexpr OperandSpec kOperands_SPAWN[] = {
    {"call", Width::U32, OperandKind::Call},
};

inline constexpr OperandSpec kOperands_CONSTRUCT[] = {
    {"type", Width::U32, OperandKind::Type},
    {"call", Width::U32, OperandKind::Call},
};

inline constexpr OperandSpec kOperands_NEW_ENUM[] = {
    {"enum", Width::U32, OperandKind::Type},
    {"variant", Width::U16, OperandKind::Value},
};

inline constexpr OperandSpec kOperands_LOAD_FIELD[] = {
    {"field", Width::U32, OperandKind::Field},
};

inline constexpr OperandSpec kOperands_STORE_FIELD[] = {
    {"field", Width::U32, OperandKind::Field},
};

inline constexpr OperandSpec kOperands_LOAD_MEMBER[] = {
    {"name", Width::U32, OperandKind::Name},
};

inline constexpr OperandSpec kOperands_STORE_MEMBER[] = {
    {"name", Width::U32, OperandKind::Name},
};

inline constexpr OperandSpec kOperands_LOAD_MEMBER_SAFE[] = {
    {"name", Width::U32, OperandKind::Name},
};

inline constexpr OperandSpec kOperands_LOAD_ENUM_MEMBER[] = {
    {"enum", Width::U32, OperandKind::Type},
    {"variant", Width::U16, OperandKind::Value},
};

inline constexpr OperandSpec kOperands_SET_LOCKS[] = {
    {"flags", Width::U8, OperandKind::Flags},
};

inline constexpr OperandSpec kOperands_CHECK_TRAIT[] = {
    {"trait", Width::U32, OperandKind::Trait},
};

inline constexpr OperandSpec kOperands_TRAIT_CAST[] = {
    {"trait", Width::U32, OperandKind::Trait},
};

inline constexpr OperandSpec kOperands_MAKE_ERROR[] = {
    {"spec", Width::U32, OperandKind::Spec},
};

inline constexpr OperandSpec kOperands_ERROR_PROPERTY[] = {
    {"property", Width::U8, OperandKind::Value},
};

inline constexpr OperandSpec kOperands_TRY_BEGIN[] = {
    {"catch", Width::I32, OperandKind::Target},
    {"finally", Width::I32, OperandKind::Target},
};

inline constexpr OperandSpec kOperands_REF_LOCAL[] = {
    {"slot", Width::U16, OperandKind::Slot},
};

inline constexpr OperandSpec kOperands_REF_GLOBAL[] = {
    {"name", Width::U32, OperandKind::Name},
};

inline constexpr OperandSpec kOperands_REF_FIELD[] = {
    {"field", Width::U32, OperandKind::Field},
};

inline constexpr OperandSpec kOperands_IMPORT[] = {
    {"module", Width::U32, OperandKind::Module},
    {"slot", Width::U16, OperandKind::Slot},
};

inline constexpr OperandSpec kOperands_IMPORT_WILDCARD[] = {
    {"module", Width::U32, OperandKind::Module},
};

inline constexpr OperandSpec kOperands_LOAD_MODULE_MEMBER[] = {
    {"module", Width::U32, OperandKind::Module},
    {"export", Width::U32, OperandKind::Export},
};

inline constexpr OperandSpec kOperands_EXPORT[] = {
    {"name", Width::U32, OperandKind::Name},
};

inline constexpr OperandSpec kOperands_TRACE_EVENT[] = {
    {"event", Width::U16, OperandKind::Event},
};

inline constexpr OperandSpec kOperands_HOST_CALL[] = {
    {"host", Width::U32, OperandKind::Host},
};

inline constexpr OperandSpec kOperands_ASSIGN_LOCAL[] = {
    {"slot", Width::U16, OperandKind::Slot},
};

inline constexpr OperandSpec kOperands_ASSIGN_NAME[] = {
    {"name", Width::U32, OperandKind::Name},
};

inline constexpr OperandSpec kOperands_MAKE_FUNCTION[] = {
    {"function", Width::U32, OperandKind::Value},
};

inline constexpr OperandSpec kOperands_LOAD_RAW[] = {
    {"slot", Width::U16, OperandKind::Slot},
};

inline constexpr OperandSpec kOperands_STORE_RAW[] = {
    {"slot", Width::U16, OperandKind::Slot},
};

inline constexpr OperandSpec kOperands_SET_TRANSFER[] = {
    {"kind", Width::U8, OperandKind::Value},
    {"target", Width::I32, OperandKind::Target},
};

inline constexpr OperandSpec kOperands_JUMP_IF_TRANSFER[] = {
    {"target", Width::I32, OperandKind::Target},
};

inline constexpr OperandSpec kOperands_LOAD_FREE[] = {
    {"name", Width::U32, OperandKind::Name},
};

inline constexpr OpcodeSpec kOpcodes[] = {
    {"NOP", 0, nullptr, 0, 0, 0, "stack"},
    {"POP", 1, nullptr, 0, 1, 0, "stack"},
    {"DUP", 2, nullptr, 0, 1, 2, "stack"},
    {"DUP2", 3, nullptr, 0, 2, 4, "stack"},
    {"SWAP", 4, nullptr, 0, 2, 2, "stack"},
    {"ROT3", 5, nullptr, 0, 3, 3, "stack"},
    {"ROT", 6, kOperands_ROT, 1, -1, -1, "stack"},
    {"LOAD_NOVA", 7, nullptr, 0, 0, 1, "literal"},
    {"LOAD_UNDEF", 8, nullptr, 0, 0, 1, "literal"},
    {"LOAD_TRUE", 9, nullptr, 0, 0, 1, "literal"},
    {"LOAD_FALSE", 10, nullptr, 0, 0, 1, "literal"},
    {"LOAD_INT", 11, kOperands_LOAD_INT, 1, 0, 1, "literal"},
    {"LOAD_BIGINT", 12, kOperands_LOAD_BIGINT, 1, 0, 1, "literal"},
    {"LOAD_NUM", 13, kOperands_LOAD_NUM, 1, 0, 1, "literal"},
    {"LOAD_CHAR", 14, kOperands_LOAD_CHAR, 1, 0, 1, "literal"},
    {"LOAD_STR", 15, kOperands_LOAD_STR, 1, 0, 1, "literal"},
    {"LOAD_CONST", 16, kOperands_LOAD_CONST, 1, 0, 1, "literal"},
    {"DECLARE_LOCAL", 17, kOperands_DECLARE_LOCAL, 3, 0, 1, "declare"},
    {"DECLARE_GLOBAL", 18, kOperands_DECLARE_GLOBAL, 3, 0, 1, "declare"},
    {"DECLARE_TYPED", 19, kOperands_DECLARE_TYPED, 2, 1, 1, "declare"},
    {"DECLARE_INFER", 20, kOperands_DECLARE_INFER, 1, 1, 1, "declare"},
    {"DECLARE_TYPED_GLOBAL", 21, kOperands_DECLARE_TYPED_GLOBAL, 2, 1, 1, "declare"},
    {"DECLARE_INFER_GLOBAL", 22, kOperands_DECLARE_INFER_GLOBAL, 1, 1, 1, "declare"},
    {"DECLARE_UNDEFINED_GLOBAL", 23, kOperands_DECLARE_UNDEFINED_GLOBAL, 3, 0, 1, "declare"},
    {"DESTRUCTURE", 24, kOperands_DESTRUCTURE, 2, 0, 1, "declare"},
    {"DECLARE_FUNCTION", 25, kOperands_DECLARE_FUNCTION, 1, 0, 1, "declare"},
    {"DECLARE_TYPE", 26, kOperands_DECLARE_TYPE, 1, 0, 1, "declare"},
    {"DECLARE_TRAIT", 27, kOperands_DECLARE_TRAIT, 1, 0, 1, "declare"},
    {"DECLARE_EXTERN", 28, kOperands_DECLARE_EXTERN, 1, 0, 0, "declare"},
    {"LOAD_LOCAL", 29, kOperands_LOAD_LOCAL, 1, 0, 1, "variable"},
    {"STORE_LOCAL", 30, kOperands_STORE_LOCAL, 1, 1, 0, "variable"},
    {"LOAD_GLOBAL", 31, kOperands_LOAD_GLOBAL, 1, 0, 1, "variable"},
    {"STORE_GLOBAL", 32, kOperands_STORE_GLOBAL, 1, 1, 0, "variable"},
    {"LOAD_NAME", 33, kOperands_LOAD_NAME, 1, 0, 1, "variable"},
    {"STORE_NAME", 34, kOperands_STORE_NAME, 1, 1, 0, "variable"},
    {"LOAD_CAPTURE", 35, kOperands_LOAD_CAPTURE, 1, 0, 1, "variable"},
    {"MAKE_CAPTURE", 36, kOperands_MAKE_CAPTURE, 1, 0, 0, "variable"},
    {"LOAD_THIS", 37, nullptr, 0, 0, 1, "variable"},
    {"COPY", 38, nullptr, 0, 1, 1, "variable"},
    {"CAST_ASSIGN", 39, kOperands_CAST_ASSIGN, 1, 1, 1, "variable"},
    {"CAST_RETURN", 40, kOperands_CAST_RETURN, 1, 1, 1, "variable"},
    {"BOX_ANY", 41, kOperands_BOX_ANY, 1, 1, 1, "variable"},
    {"UNBOX_ANY", 42, nullptr, 0, 1, 1, "variable"},
    {"MAKE_ARRAY", 43, kOperands_MAKE_ARRAY, 1, -1, 1, "container"},
    {"MAKE_ARRAY_TYPED", 44, kOperands_MAKE_ARRAY_TYPED, 2, -1, 1, "container"},
    {"MAKE_TUPLE", 45, kOperands_MAKE_TUPLE, 1, -1, 1, "container"},
    {"MAKE_TUPLE_TYPED", 46, kOperands_MAKE_TUPLE_TYPED, 2, -1, 1, "container"},
    {"MAKE_MAP", 47, kOperands_MAKE_MAP, 1, -1, 1, "container"},
    {"MAKE_MAP_TYPED", 48, kOperands_MAKE_MAP_TYPED, 2, -1, 1, "container"},
    {"MAKE_SET", 49, kOperands_MAKE_SET, 1, -1, 1, "container"},
    {"MAKE_SET_TYPED", 50, kOperands_MAKE_SET_TYPED, 2, -1, 1, "container"},
    {"MAKE_EMPTY_MAP", 51, nullptr, 0, 0, 1, "container"},
    {"MAKE_EMPTY_SET", 52, nullptr, 0, 0, 1, "container"},
    {"INDEX_GET", 53, nullptr, 0, 2, 1, "container"},
    {"INDEX_SET", 54, nullptr, 0, 3, 1, "container"},
    {"SLICE", 55, nullptr, 0, 3, 1, "container"},
    {"SIZE", 56, nullptr, 0, 1, 1, "container"},
    {"ITER_NEW", 57, nullptr, 0, 1, 1, "container"},
    {"ITER_NEXT", 58, kOperands_ITER_NEXT, 1, 1, 1, "container"},
    {"ADD", 59, nullptr, 0, 2, 1, "arithmetic"},
    {"SUB", 60, nullptr, 0, 2, 1, "arithmetic"},
    {"MUL", 61, nullptr, 0, 2, 1, "arithmetic"},
    {"DIV", 62, nullptr, 0, 2, 1, "arithmetic"},
    {"MOD", 63, nullptr, 0, 2, 1, "arithmetic"},
    {"NEG", 64, nullptr, 0, 1, 1, "arithmetic"},
    {"NOT", 65, nullptr, 0, 1, 1, "arithmetic"},
    {"EQ", 66, nullptr, 0, 2, 1, "arithmetic"},
    {"NEQ", 67, nullptr, 0, 2, 1, "arithmetic"},
    {"LT", 68, nullptr, 0, 2, 1, "arithmetic"},
    {"LE", 69, nullptr, 0, 2, 1, "arithmetic"},
    {"GT", 70, nullptr, 0, 2, 1, "arithmetic"},
    {"GE", 71, nullptr, 0, 2, 1, "arithmetic"},
    {"EQ_TYPED", 72, nullptr, 0, 2, 1, "arithmetic"},
    {"NEQ_TYPED", 73, nullptr, 0, 2, 1, "arithmetic"},
    {"LT_TYPED", 74, nullptr, 0, 2, 1, "arithmetic"},
    {"LE_TYPED", 75, nullptr, 0, 2, 1, "arithmetic"},
    {"GT_TYPED", 76, nullptr, 0, 2, 1, "arithmetic"},
    {"GE_TYPED", 77, nullptr, 0, 2, 1, "arithmetic"},
    {"CONCAT_STR", 78, kOperands_CONCAT_STR, 1, -1, 1, "arithmetic"},
    {"TO_STRING", 79, nullptr, 0, 1, 1, "arithmetic"},
    {"TO_BOOL", 80, nullptr, 0, 1, 1, "arithmetic"},
    {"REVERSE", 81, nullptr, 0, 1, 1, "arithmetic"},
    {"CAST", 82, kOperands_CAST, 1, 1, 1, "arithmetic"},
    {"TYPE_CHECK", 83, kOperands_TYPE_CHECK, 1, 1, 1, "arithmetic"},
    {"TYPE_CHECK_NOT", 84, kOperands_TYPE_CHECK_NOT, 1, 1, 1, "arithmetic"},
    {"TYPE_CHECK_VALUE", 85, nullptr, 0, 2, 1, "arithmetic"},
    {"IS_NOVA", 86, nullptr, 0, 1, 1, "arithmetic"},
    {"IS_DEFINED", 87, nullptr, 0, 1, 1, "arithmetic"},
    {"IS_WEAK", 88, nullptr, 0, 1, 1, "arithmetic"},
    {"JUMP", 89, kOperands_JUMP, 1, 0, 0, "control"},
    {"JUMP_IF_FALSE", 90, kOperands_JUMP_IF_FALSE, 1, 1, 0, "control"},
    {"JUMP_IF_TRUE", 91, kOperands_JUMP_IF_TRUE, 1, 1, 0, "control"},
    {"JUMP_IF_FALSE_KEEP", 92, kOperands_JUMP_IF_FALSE_KEEP, 1, 1, 1, "control"},
    {"JUMP_IF_TRUE_KEEP", 93, kOperands_JUMP_IF_TRUE_KEEP, 1, 1, 1, "control"},
    {"JUMP_IF_NOVA", 94, kOperands_JUMP_IF_NOVA, 1, 1, 0, "control"},
    {"JUMP_IF_NOT_NOVA", 95, kOperands_JUMP_IF_NOT_NOVA, 1, 1, 0, "control"},
    {"MATCH", 96, kOperands_MATCH, 2, 1, 0, "control"},
    {"RETURN", 97, nullptr, 0, 1, 0, "control"},
    {"CHECK_CANCEL", 98, nullptr, 0, 0, 0, "control"},
    {"CALL", 99, kOperands_CALL, 1, -1, 1, "call"},
    {"CALL_VALUE", 100, kOperands_CALL_VALUE, 1, -1, 1, "call"},
    {"CALL_METHOD", 101, kOperands_CALL_METHOD, 1, -1, 1, "call"},
    {"CALL_STATIC", 102, kOperands_CALL_STATIC, 1, -1, 1, "call"},
    {"CALL_MODULE", 103, kOperands_CALL_MODULE, 1, -1, 1, "call"},
    {"CALL_NATIVE", 104, kOperands_CALL_NATIVE, 1, -1, 1, "call"},
    {"CALL_BUILTIN", 105, kOperands_CALL_BUILTIN, 1, -1, 1, "call"},
    {"CALL_TRAIT", 106, kOperands_CALL_TRAIT, 1, -1, 1, "call"},
    {"CALL_OPERATOR", 107, kOperands_CALL_OPERATOR, 1, -1, 1, "call"},
    {"CALL_EXTERN", 108, kOperands_CALL_EXTERN, 1, -1, 1, "call"},
    {"CALL_ASYNC", 109, kOperands_CALL_ASYNC, 1, -1, 1, "call"},
    {"CALL_ASYNC_METHOD", 110, kOperands_CALL_ASYNC_METHOD, 1, -1, 1, "call"},
    {"SPAWN", 111, kOperands_SPAWN, 1, -1, 1, "call"},
    {"AWAIT", 112, nullptr, 0, 1, 1, "call"},
    {"CONSTRUCT", 113, kOperands_CONSTRUCT, 2, -1, 1, "object"},
    {"NEW_ENUM", 114, kOperands_NEW_ENUM, 2, 0, 1, "object"},
    {"LOAD_FIELD", 115, kOperands_LOAD_FIELD, 1, 1, 1, "object"},
    {"STORE_FIELD", 116, kOperands_STORE_FIELD, 1, 2, 0, "object"},
    {"LOAD_MEMBER", 117, kOperands_LOAD_MEMBER, 1, 1, 1, "object"},
    {"STORE_MEMBER", 118, kOperands_STORE_MEMBER, 1, 2, 1, "object"},
    {"LOAD_MEMBER_SAFE", 119, kOperands_LOAD_MEMBER_SAFE, 1, 1, 1, "object"},
    {"LOAD_ENUM_MEMBER", 120, kOperands_LOAD_ENUM_MEMBER, 2, 0, 1, "object"},
    {"SET_LOCKS", 121, kOperands_SET_LOCKS, 1, 1, 0, "object"},
    {"CHECK_TRAIT", 122, kOperands_CHECK_TRAIT, 1, 1, 1, "trait"},
    {"TRAIT_CAST", 123, kOperands_TRAIT_CAST, 1, 1, 1, "trait"},
    {"MAKE_ERROR", 124, kOperands_MAKE_ERROR, 1, -1, 1, "error"},
    {"ERROR_PROPERTY", 125, kOperands_ERROR_PROPERTY, 1, 1, 1, "error"},
    {"THROW", 126, nullptr, 0, 1, 0, "error"},
    {"PROPAGATE", 127, nullptr, 0, 1, 1, "error"},
    {"TRY_BEGIN", 128, kOperands_TRY_BEGIN, 2, 0, 0, "error"},
    {"TRY_END", 129, nullptr, 0, 0, 0, "error"},
    {"FINALLY_END", 130, nullptr, 0, 0, 0, "error"},
    {"RETHROW", 131, nullptr, 0, 1, 0, "error"},
    {"REF_LOCAL", 132, kOperands_REF_LOCAL, 1, 0, 1, "reference"},
    {"REF_GLOBAL", 133, kOperands_REF_GLOBAL, 1, 0, 1, "reference"},
    {"REF_FIELD", 134, kOperands_REF_FIELD, 1, 1, 1, "reference"},
    {"REF_INDEX", 135, nullptr, 0, 2, 1, "reference"},
    {"LOAD_REF", 136, nullptr, 0, 1, 1, "reference"},
    {"STORE_REF", 137, nullptr, 0, 2, 0, "reference"},
    {"IMPORT", 138, kOperands_IMPORT, 2, 0, 0, "module"},
    {"IMPORT_WILDCARD", 139, kOperands_IMPORT_WILDCARD, 1, 0, 0, "module"},
    {"LOAD_MODULE_MEMBER", 140, kOperands_LOAD_MODULE_MEMBER, 2, 0, 1, "module"},
    {"LOAD_PROJECT", 141, nullptr, 0, 0, 1, "module"},
    {"EXPORT", 142, kOperands_EXPORT, 1, 1, 0, "module"},
    {"TRACE_EVENT", 143, kOperands_TRACE_EVENT, 1, 0, 0, "debug"},
    {"HOST_CALL", 144, kOperands_HOST_CALL, 1, -1, 1, "debug"},
    {"ASSIGN_LOCAL", 145, kOperands_ASSIGN_LOCAL, 1, 1, 0, "slot"},
    {"ASSIGN_NAME", 146, kOperands_ASSIGN_NAME, 1, 1, 0, "slot"},
    {"MAKE_FUNCTION", 147, kOperands_MAKE_FUNCTION, 1, 0, 1, "function"},
    {"MAKE_SPREAD", 148, nullptr, 0, 1, 1, "stack"},
    {"LOAD_RAW", 149, kOperands_LOAD_RAW, 1, 0, 1, "slot"},
    {"STORE_RAW", 150, kOperands_STORE_RAW, 1, 1, 0, "slot"},
    {"ADD_TYPED", 151, nullptr, 0, 2, 1, "arithmetic"},
    {"SUB_TYPED", 152, nullptr, 0, 2, 1, "arithmetic"},
    {"MUL_TYPED", 153, nullptr, 0, 2, 1, "arithmetic"},
    {"DIV_TYPED", 154, nullptr, 0, 2, 1, "arithmetic"},
    {"MOD_TYPED", 155, nullptr, 0, 2, 1, "arithmetic"},
    {"SET_RETURN", 156, nullptr, 0, 1, 0, "control"},
    {"SET_TRANSFER", 157, kOperands_SET_TRANSFER, 2, 0, 0, "control"},
    {"JUMP_IF_TRANSFER", 158, kOperands_JUMP_IF_TRANSFER, 1, 0, 0, "control"},
    {"APPLY_TRANSFER", 159, nullptr, 0, 0, 0, "control"},
    {"ABANDON_FINALLY", 160, nullptr, 0, 0, 0, "control"},
    {"LOAD_FREE", 161, kOperands_LOAD_FREE, 1, 0, 1, "slot"},
    {"SCOPE_PUSH", 162, nullptr, 0, 0, 0, "control"},
    {"SCOPE_POP", 163, nullptr, 0, 0, 0, "control"},
};

inline constexpr std::size_t kOpcodeCount = sizeof(kOpcodes) / sizeof(kOpcodes[0]);

inline constexpr std::uint16_t kFormatVersion = 1;
inline constexpr const char* kLanguageVersion = "0.22.0";

} // namespace generated

} // namespace pwb
