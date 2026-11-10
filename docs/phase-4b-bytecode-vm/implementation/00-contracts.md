# VM Implementation Contracts

Status: binding interface contract for the Phase 4B implementation. Every module
listed here must match these names exactly. Tests and the compiler rely on them.

This file is the single reference for cross module interfaces. The design
documents in the parent directory define semantics. This file defines code.

Conventions:

- Package root is `src/vm`.
- Python 3.12 or newer.
- All public functions use explicit type hints.
- Runtime values are the existing `PowangAny` classes from
  `src.powang_types`. The VM never invents a second value model.
- Language errors use `PowangError` and the helpers in `src.error`.
- Plain punctuation in every comment, docstring and message. No em dashes, no
  en dashes, no semicolons, no decorative glyphs.

## 1. Package layout

```text
src/vm/__init__.py        public exports and engine constants
src/vm/opcodes.py         OpcodeSpec, Operand, registry, encode and decode
src/vm/image.py           SourceSpan, ExceptionEntry, CodeObject, CallSite,
                          PatternDescriptor, TypeInfo, TraitInfo, FunctionInfo,
                          ModuleInfo, ProgramImage, binary codec
src/vm/builder.py         Builder, Label, operand encoding, label resolution
src/vm/verifier.py        VerificationError, verify_code, verify_image
src/vm/values.py          tag mapping, truthiness, constants, equality, hashing,
                          SpreadValue wrapper
src/vm/frames.py          LocalStore, HandlerEntry, VMFrame
src/vm/compiler.py        Compiler, compile_ast, compile_source
src/vm/interpreter.py     VM, run, execution loop, handler tables
src/vm/dispatch.py        call resolution and argument binding
src/vm/declarations.py    type, trait, enum and extern declaration runtime
src/vm/modules.py         VM module evaluation and session state
src/vm/tasks.py           lazy and worker task helpers for the VM
src/vm/host.py            builtin, native, extern and project access
src/vm/errors.py          error value conversion and unwinding helpers
src/vm/disasm.py          disassemble_code, disassemble_image
src/vm/trace.py           TraceEvent, TraceSink, TextTraceSink
src/vm/differential.py    run_pair, DiffResult
src/vm/bench.py           benchmark corpus and runner
src/vm/cli.py             powang vm subcommand
```

## 2. Opcode registry

`src/vm/opcodes.py` defines:

```python
WIDTHS: dict[str, int] = {
    "u8": 1, "u16": 2, "u32": 4, "i32": 4, "i64": 8, "f64": 8,
}

@dataclass(frozen=True)
class Operand:
    name: str
    width: str
    kind: str = "value"

@dataclass(frozen=True)
class OpcodeSpec:
    name: str
    opcode: int
    operands: tuple[Operand, ...]
    stack_in: int
    stack_out: int
    verifier: str
    handler: str
    doc: str = ""

    @property
    def size(self) -> int: ...          # 1 + sum widths

OPCODES: tuple[OpcodeSpec, ...]
BY_NAME: dict[str, OpcodeSpec]
BY_OPCODE: dict[int, OpcodeSpec]

def spec(name: str) -> OpcodeSpec
def encode_operands(opcode_spec: OpcodeSpec, values: Sequence[int | float]) -> bytes
def decode_operands(opcode_spec: OpcodeSpec, data: bytes, offset: int) -> tuple[dict[str, int | float], int]
def decode_instruction(data: bytes, offset: int) -> tuple[OpcodeSpec, dict[str, int | float], int]
```

Operand kinds are validation hints used by the verifier and disassembler:
`value`, `slot`, `target`, `const`, `spec`, `call`, `pattern`, `module`,
`type`, `trait`, `field`, `name`, `export`, `host`, `event`, `flags`.

`stack_in` and `stack_out` use `-1` to mean variable height. The verifier owns
the exact rule for variable height opcodes.

The opcode list is fixed and ordered. Opcode numbers are assigned in this
order starting at 0. Appending a new opcode at the end is allowed. Reordering
or renumbering requires a bytecode format version bump.

```text
NOP POP DUP DUP2 SWAP ROT3 ROT
LOAD_NOVA LOAD_UNDEF LOAD_TRUE LOAD_FALSE LOAD_INT LOAD_BIGINT LOAD_NUM
LOAD_CHAR LOAD_STR LOAD_CONST
DECLARE_LOCAL DECLARE_GLOBAL DECLARE_TYPED DECLARE_INFER DECLARE_TYPED_GLOBAL
DECLARE_INFER_GLOBAL DECLARE_UNDEFINED_GLOBAL DESTRUCTURE
DECLARE_FUNCTION DECLARE_TYPE DECLARE_TRAIT DECLARE_EXTERN
LOAD_LOCAL STORE_LOCAL LOAD_GLOBAL STORE_GLOBAL LOAD_NAME STORE_NAME
LOAD_CAPTURE MAKE_CAPTURE LOAD_THIS COPY CAST_ASSIGN CAST_RETURN
BOX_ANY UNBOX_ANY
MAKE_ARRAY MAKE_ARRAY_TYPED MAKE_TUPLE MAKE_TUPLE_TYPED MAKE_MAP
MAKE_MAP_TYPED MAKE_SET MAKE_SET_TYPED MAKE_EMPTY_MAP MAKE_EMPTY_SET
INDEX_GET INDEX_SET SLICE SIZE ITER_NEW ITER_NEXT
ADD SUB MUL DIV MOD NEG NOT EQ NEQ LT LE GT GE
EQ_TYPED NEQ_TYPED LT_TYPED LE_TYPED GT_TYPED GE_TYPED
CONCAT_STR TO_STRING TO_BOOL REVERSE CAST TYPE_CHECK TYPE_CHECK_NOT
TYPE_CHECK_VALUE IS_NOVA IS_DEFINED IS_WEAK
JUMP JUMP_IF_FALSE JUMP_IF_TRUE JUMP_IF_FALSE_KEEP JUMP_IF_TRUE_KEEP
JUMP_IF_NOVA JUMP_IF_NOT_NOVA MATCH RETURN CHECK_CANCEL
CALL CALL_VALUE CALL_METHOD CALL_STATIC CALL_MODULE CALL_NATIVE CALL_BUILTIN
CALL_TRAIT CALL_OPERATOR CALL_EXTERN CALL_ASYNC CALL_ASYNC_METHOD SPAWN AWAIT
CONSTRUCT NEW_ENUM LOAD_FIELD STORE_FIELD LOAD_MEMBER STORE_MEMBER
LOAD_MEMBER_SAFE LOAD_ENUM_MEMBER SET_LOCKS
CHECK_TRAIT TRAIT_CAST
MAKE_ERROR ERROR_PROPERTY THROW PROPAGATE TRY_BEGIN TRY_END FINALLY_END RETHROW
REF_LOCAL REF_GLOBAL REF_FIELD REF_INDEX LOAD_REF STORE_REF
IMPORT IMPORT_WILDCARD LOAD_MODULE_MEMBER LOAD_PROJECT EXPORT
TRACE_EVENT HOST_CALL
```

Operand layouts:

| Opcode | Operands | stack_in | stack_out |
|---|---|---|---|
| NOP | none | 0 | 0 |
| POP | none | 1 | 0 |
| DUP | none | 1 | 2 |
| DUP2 | none | 2 | 4 |
| SWAP | none | 2 | 2 |
| ROT3 | none | 3 | 3 |
| ROT | count u16 | -1 | -1 |
| LOAD_NOVA, LOAD_UNDEF, LOAD_TRUE, LOAD_FALSE | none | 0 | 1 |
| LOAD_INT | value i64 | 0 | 1 |
| LOAD_BIGINT | const u32 | 0 | 1 |
| LOAD_NUM | value f64 | 0 | 1 |
| LOAD_CHAR | value u32 | 0 | 1 |
| LOAD_STR | const u32 | 0 | 1 |
| LOAD_CONST | const u32 | 0 | 1 |
| DECLARE_LOCAL | slot u16, spec u32, flags u8 | 0 | 1 |
| DECLARE_GLOBAL | name u32, spec u32, flags u8 | 0 | 1 |
| DECLARE_TYPED | slot u16, spec u32 | 1 | 1 |
| DECLARE_INFER | slot u16 | 1 | 1 |
| DECLARE_TYPED_GLOBAL | name u32, spec u32 | 1 | 1 |
| DECLARE_INFER_GLOBAL | name u32 | 1 | 1 |
| DECLARE_UNDEFINED_GLOBAL | name u32, spec u32, flags u8 | 0 | 1 |
| DESTRUCTURE | descriptor u32, source_slot u16 | 0 | 1 |
| DECLARE_FUNCTION | function u32 | 0 | 1 |
| DECLARE_TYPE | type u32 | 0 | 1 |
| DECLARE_TRAIT | trait u32 | 0 | 1 |
| DECLARE_EXTERN | extern u32 | 0 | 0 |
| LOAD_LOCAL | slot u16 | 0 | 1 |
| STORE_LOCAL | slot u16 | 1 | 0 |
| LOAD_GLOBAL | name u32 | 0 | 1 |
| STORE_GLOBAL | name u32 | 1 | 0 |
| LOAD_NAME | name u32 | 0 | 1 |
| STORE_NAME | name u32 | 1 | 0 |
| LOAD_CAPTURE | index u16 | 0 | 1 |
| MAKE_CAPTURE | slot u16 | 0 | 0 |
| LOAD_THIS | none | 0 | 1 |
| COPY | none | 1 | 1 |
| CAST_ASSIGN, CAST_RETURN | spec u32 | 1 | 1 |
| BOX_ANY | spec u32 | 1 | 1 |
| UNBOX_ANY | none | 1 | 1 |
| MAKE_ARRAY, MAKE_TUPLE, MAKE_SET | count u16 | -1 | 1 |
| MAKE_ARRAY_TYPED, MAKE_TUPLE_TYPED, MAKE_SET_TYPED | spec u32, count u16 | -1 | 1 |
| MAKE_MAP | count u16 | -1 | 1 |
| MAKE_MAP_TYPED | spec u32, count u16 | -1 | 1 |
| MAKE_EMPTY_MAP, MAKE_EMPTY_SET | none | 0 | 1 |
| INDEX_GET | none | 2 | 1 |
| INDEX_SET | none | 3 | 1 |
| SLICE | none | 3 | 1 |
| SIZE | none | 1 | 1 |
| ITER_NEW | none | 1 | 1 |
| ITER_NEXT | target i32 | 1 | 2 |
| ADD SUB MUL DIV MOD | none | 2 | 1 |
| NEG | none | 1 | 1 |
| NOT | none | 1 | 1 |
| EQ NEQ LT LE GT GE and typed variants | none | 2 | 1 |
| CONCAT_STR | count u16 | -1 | 1 |
| TO_STRING | none | 1 | 1 |
| TO_BOOL | none | 1 | 1 |
| REVERSE | none | 1 | 1 |
| CAST | spec u32 | 1 | 1 |
| TYPE_CHECK, TYPE_CHECK_NOT | spec u32 | 1 | 1 |
| TYPE_CHECK_VALUE | none | 2 | 1 |
| IS_NOVA, IS_DEFINED, IS_WEAK | none | 1 | 1 |
| JUMP | target i32 | 0 | 0 |
| JUMP_IF_FALSE, JUMP_IF_TRUE | target i32 | 1 | 0 |
| JUMP_IF_FALSE_KEEP, JUMP_IF_TRUE_KEEP | target i32 | 1 | 1 |
| JUMP_IF_NOVA, JUMP_IF_NOT_NOVA | target i32 | 1 | 0 |
| MATCH | pattern u32, target i32 | 1 | 0 |
| RETURN | none | 1 | 0 |
| CHECK_CANCEL | none | 0 | 0 |
| CALL, CALL_BUILTIN, CALL_EXTERN | call u32 | -1 | 1 |
| CALL_VALUE | call u32 | -1 | 1 |
| CALL_METHOD, CALL_STATIC, CALL_MODULE, CALL_NATIVE, CALL_TRAIT, CALL_OPERATOR | call u32 | -1 | 1 |
| CALL_ASYNC, CALL_ASYNC_METHOD, SPAWN | call u32 | -1 | 1 |
| AWAIT | none | 1 | 1 |
| CONSTRUCT | type u32, call u32 | -1 | 1 |
| NEW_ENUM | enum u32, variant u16 | 0 | 1 |
| LOAD_FIELD | field u32 | 1 | 1 |
| STORE_FIELD | field u32 | 2 | 1 |
| LOAD_MEMBER, LOAD_MEMBER_SAFE | name u32 | 1 | 1 |
| STORE_MEMBER | name u32 | 2 | 1 |
| LOAD_ENUM_MEMBER | enum u32, variant u16 | 0 | 1 |
| SET_LOCKS | flags u8 | 1 | 0 |
| CHECK_TRAIT, TRAIT_CAST | trait u32 | 1 | 1 |
| MAKE_ERROR | spec u32 | -1 | 1 |
| ERROR_PROPERTY | property u8 | 1 | 1 |
| THROW | none | 1 | 0 |
| PROPAGATE | none | 1 | 1 |
| TRY_BEGIN | catch i32, finally i32 | 0 | 0 |
| TRY_END, FINALLY_END | none | 0 | 0 |
| RETHROW | none | 1 | 0 |
| REF_LOCAL | slot u16 | 0 | 1 |
| REF_GLOBAL | name u32 | 0 | 1 |
| REF_FIELD | field u32 | 1 | 1 |
| REF_INDEX | none | 2 | 1 |
| LOAD_REF, STORE_REF | none | 1 or 2 | 1 or 0 |
| IMPORT | module u32, slot u16 | 0 | 0 |
| IMPORT_WILDCARD | module u32 | 0 | 0 |
| LOAD_MODULE_MEMBER | module u32, export u32 | 0 | 1 |
| LOAD_PROJECT | none | 0 | 1 |
| EXPORT | name u32 | 1 | 0 |
| TRACE_EVENT | event u16 | 0 | 0 |
| HOST_CALL | host u32 | -1 | 1 |

## 3. Program image

```python
FORMAT_MAGIC = b"PWB1"
FORMAT_VERSION = 1
LANGUAGE_VERSION = "0.21.0"

@dataclass(frozen=True)
class SourceSpan:
    file_id: int
    start_line: int
    start_column: int
    end_line: int
    end_column: int

@dataclass(frozen=True)
class ExceptionEntry:
    start_ip: int
    end_ip: int
    catch_ip: int
    finally_ip: int
    resume_ip: int
    stack_depth: int
    local_watermark: int
    kind: str                 # "catch" or "finally"

@dataclass(frozen=True)
class Constant:
    kind: str                 # "nova", "bool", "int", "bigint", "num", "str",
                              # "char", "ast", "call", "pattern", "spec",
                              # "type", "trait", "function", "extern",
                              # "descriptor", "tuple"
    value: Any

@dataclass
class CodeObject:
    name: str
    qualname: str
    source_file: int
    parameter_count: int
    local_count: int
    capture_count: int
    max_stack: int
    max_frame_depth: int
    bytecode: bytes
    constant_indices: tuple[int, ...]
    constants: tuple[Constant, ...]
    spans: tuple[SourceSpan, ...]
    span_table: tuple[int, ...]
    exception_table: tuple[ExceptionEntry, ...]
    local_names: tuple[str, ...]
    parameter_names: tuple[str, ...]
    return_spec: int
    flags: int
    trait_name: str | None
    operator_trait: str | None
    fallback_ast: Any

    @property
    def is_async(self) -> bool
    @property
    def is_variadic(self) -> bool
    @property
    def is_method(self) -> bool
    @property
    def is_static(self) -> bool

@dataclass
class CallSite:
    dispatch: str             # call, value, method, static, module, native,
                              # builtin, trait, operator, extern, async,
                              # async_method, spawn, construct
    name: str
    module: str | None
    type_name: str | None
    trait_name: str | None
    operator_trait: str | None
    native_type: str | None
    positional_count: int
    argument_kinds: tuple[str, ...]      # positional, named, spread
    argument_names: tuple[str, ...]      # name per argument or ""
    type_argument_count: int
    return_spec: int
    is_async: bool
    callee_ast: Any
    method_ast: Any

@dataclass
class PatternDescriptor:
    kind: str
    literal: Any
    bindings: tuple[tuple[str, int], ...]
    nested: tuple["PatternDescriptor", ...]
    type_name: str | None
    fields: tuple[tuple[str, "PatternDescriptor"], ...]
    rest_slot: int
    start_ast: Any
    end_ast: Any

@dataclass
class TypeInfo:
    name: str
    kind: str                 # object, enum
    type_parameters: tuple[str, ...]
    properties: tuple[tuple[bool, str, int, str | None], ...]
    methods: tuple[tuple[bool, str, int, str | None, bool], ...]
    variants: tuple[str, ...]

@dataclass
class TraitInfo:
    name: str
    properties: tuple[str, ...]
    methods: tuple[tuple[str, int, bool], ...]

@dataclass
class FunctionInfo:
    name: str
    code_index: int
    args: Any
    min_argc: int
    return_node: Any
    flags: dict[str, Any]
    body: Any

@dataclass
class ModuleInfo:
    name: str
    path: str
    code_index: int
    imports: tuple[Any, ...]
    exports: tuple[tuple[str, str], ...]

@dataclass
class ProgramImage:
    format_version: int
    language_version: str
    flags: int
    entry_module: int
    entry_code: int
    modules: list[ModuleInfo]
    types: list[TypeInfo]
    traits: list[TraitInfo]
    functions: list[FunctionInfo]
    constants: list[Constant]
    call_sites: list[CallSite]
    patterns: list[PatternDescriptor]
    type_specs: list[Any]
    sources: list[str]
    global_names: list[str]
    strings: list[str]
    debug_lines: list[Any]
    codes: list[CodeObject]

    def code(self, index: int) -> CodeObject
    def constant(self, index: int) -> Constant
    def call_site(self, index: int) -> CallSite
    def pattern(self, index: int) -> PatternDescriptor
    def type_info(self, index: int) -> TypeInfo
    def trait_info(self, index: int) -> TraitInfo
    def function_info(self, index: int) -> FunctionInfo
    def module_info(self, index: int) -> ModuleInfo
    def to_bytes(self) -> bytes
    @classmethod
    def from_bytes(cls, data: bytes) -> "ProgramImage"

def write_image(image: ProgramImage, path: str | Path) -> None
def read_image(path: str | Path) -> ProgramImage
```

`constant_indices` and `constants` coexist so an image can be decoded without
a global pool. The compiler fills both with the same pool indices and objects.
For serialization, write each code object's constant table inline.

Serialization format:

- Header: magic `PWB1`, u16 format version, u16 flags, UTF-8 language version
  (u16 length + bytes), u32 table count, then each table as u32 byte length
  plus bytes, then u32 CRC32 of everything before the checksum.
- Every table uses little-endian fixed width integers.
- Strings are u32 length plus UTF-8 bytes.
- Constants are u8 kind tag plus a kind specific body. AST and descriptor
  constants are encoded as UTF-8 JSON produced by `values.encode_constant_json`
  so the image is deterministic.
- Code bytecode is u32 length plus raw bytes. `span_table` is one u32 per
  instruction. Exception entries are fixed records.

## 4. Builder

```python
@dataclass(frozen=True)
class Label:
    id: int

class Builder:
    def __init__(self, name: str, qualname: str | None = None,
                 source_file: int = 0) -> None
    def emit(self, opcode: str, *operands: int | float,
             span: int = 0) -> int
    def emit_label(self, label: Label) -> None
    def new_label(self) -> Label
    def place(self, label: Label) -> None
    def patch(self) -> None
    def new_constant(self, kind: str, value: Any) -> int
    def add_span(self, span: SourceSpan) -> int
    def declare_local(self, name: str) -> int
    def reserve_local(self) -> int
    def set_parameter_names(self, names: Sequence[str]) -> None
    def finish(self, *, local_count: int | None = None,
               capture_count: int = 0,
               flags: int = 0,
               return_spec: int = -1,
               trait_name: str | None = None,
               operator_trait: str | None = None,
               fallback_ast: Any = None,
               exception_table: Sequence[ExceptionEntry] = (),
               ) -> CodeObject
    def stack_effect_bound(self) -> int
```

The builder stores instructions as `(opcode, operands, span)` and resolves
labels in `finish`. `emit` validates operand count, width and integer range.
`patch` is idempotent. `finish` raises `ValueError` on an unplaced label, on a
jump operand that names no label, or on a label placed twice.

`new_constant` deduplicates by `(kind, stable_key(value))`. Constants are pooled
per code object. `add_span` deduplicates identical spans.

## 5. Verifier

```python
class VerificationError(Exception):
    pass

def verify_code(code: CodeObject, image: ProgramImage | None = None,
                strict: bool = True) -> None
def verify_image(image: ProgramImage, strict: bool = True) -> None
```

Rules:

- Unknown opcode, truncated instruction, operand out of width.
- Constant index in range.
- Slot index below `local_count`.
- Jump target is an instruction boundary inside the code object.
- Conditional jump stack height is at least one.
- Stack underflow.
- Merge point stack height mismatch.
- `local_count`, `capture_count`, `parameter_count` not negative.
- Parameter names count equals `parameter_count` when names exist.
- Exception ranges: start and end are instruction boundaries, start < end,
  end <= len(code), catch and finally targets are instruction boundaries or
  negative, stack depth not negative, local watermark not negative.
- `span_table` length equals instruction count when it is non empty and every
  span index is in range.
- Return type spec index in range or negative.
- `max_stack` is at least the computed maximum in strict mode.
- Every reachable path ends in `RETURN` in strict mode.
- Call site and pattern indices in range when an image is provided.
- Type, trait, function, module and field indices in range when an image is
  provided.
- Reference lifetime: `STORE_LOCAL`, `STORE_GLOBAL`, `STORE_NAME`, `STORE_FIELD`,
  `STORE_REF`, `INDEX_SET`, `MAKE_ARRAY`, `MAKE_TUPLE`, `MAKE_MAP`, `MAKE_SET`
  and call opcodes reject a statically known `REF_*` producer immediately
  before them when the verifier can prove it. The runtime enforces the same
  rule at value level for dynamic cases.

`verify_image` verifies every code object and all cross table references.

## 6. Values

```python
TAGS: dict[str, str]
def tag_of(value: PowangAny) -> str
def truthy(value: PowangAny) -> bool
def is_nova(value: PowangAny) -> bool
def is_defined(value: PowangAny) -> bool
def is_weak(value: PowangAny) -> bool
def nova() -> PowangNova
def copy_value(value: PowangAny) -> PowangAny
def unwrap(value: PowangAny) -> PowangAny
def constant_to_value(constant: Constant) -> PowangAny
def value_to_constant_kind(value: PowangAny) -> str | None
def value_to_constant(value: PowangAny) -> Constant
def stable_key(value: Any) -> str
def encode_constant_json(value: Any) -> str
def decode_constant_json(text: str) -> Any

class SpreadValue:
    __slots__ = ("value",)
    def __init__(self, value: PowangAny) -> None

def spread_values(value: PowangAny) -> list[PowangAny]
```

`stable_key` must be deterministic across runs. AST nodes and type nodes are
keyed by JSON with token enums rendered by their fully qualified enum name.

## 7. Frames

```python
class LocalStore(MutableMapping[str, PowangAny]):
    """Name view over a contiguous slot array plus per frame tables."""
    def __init__(self, names: Sequence[str], values: list[PowangAny] | None = None)
    def slot(self, name: str) -> int | None
    def bind_slot(self, slot: int, name: str) -> None
    def add_slot(self, name: str) -> int
    def value_at(self, slot: int) -> PowangAny
    def set_at(self, slot: int, value: PowangAny) -> None

@dataclass
class HandlerEntry:
    start_ip: int
    end_ip: int
    catch_ip: int
    finally_ip: int
    resume_ip: int
    stack_depth: int
    local_watermark: int
    kind: str
    pending_error: BaseException | None = None
    pending_return: PowangAny | None = None
    state: str = "active"

class VMFrame:
    def __init__(self, code: CodeObject, locals: LocalStore,
                 functions: dict[str, list[PowangFunction]],
                 types: dict[str, PowangObjectType],
                 wildcards: dict[str, str],
                 module_scope: "ModuleScope",
                 receiver: PowangObjectType | None = None,
                 closure: Any = None,
                 task: PowangTask | None = None,
                 is_function: bool = True) -> None
    stack: list[PowangAny]
    ip: int
    handlers: list[HandlerEntry]
    span_index: int
    def push(self, value: PowangAny) -> None
    def pop(self) -> PowangAny
    def peek(self) -> PowangAny
    def require_stack(self, count: int, opname: str) -> None
    def scope_variables(self) -> LocalStore
```

`LocalStore` behaves exactly like the dictionary the tree walker uses for
`ScopeStack.variables`, including `get`, `setdefault`, `items`, `values`,
`keys`, `__contains__`, `__getitem__`, `__setitem__` and `__delitem__`.
Iteration yields declared names in slot order.

## 8. Compiler

```python
class CompileError(PowangError):
    pass

def compile_ast(program_ast: list[DictRepr], *, path: str | Path,
                module_name: str = "main", state=None,
                repl: bool = False) -> ProgramImage
def compile_source(source: str, *, path: str | Path,
                   module_name: str = "main", check: bool = False,
                   state=None, repl: bool = False) -> ProgramImage
```

`compile_source` parses with `Parser`, applies `simplify_program`, optionally
runs `type_check` and raises the first `PowangError` unchanged. It then calls
`compile_ast`.

The compiler must lower every `ParserTokenType` and every expression literal
kind. Complex declarations are emitted as one instruction with a descriptor
constant built from the AST. The descriptor shape is defined in
`src/vm/declarations.py` runtime handlers and documented in the phase plans.

## 9. Interpreter

```python
class VMRunOptions:
    trace: bool = False
    trace_sink: Any = None
    verify: bool = True
    trusted: bool = False
    instruction_budget: int = 0
    max_frames: int = 900

class VM:
    def __init__(self, state, image: ProgramImage,
                 options: VMRunOptions | None = None) -> None
    def run(self) -> PowangAny
    def run_code(self, code: CodeObject, arguments: list[PowangAny] | None = None,
                 receiver: PowangObjectType | None = None,
                 closure: Any = None, task: PowangTask | None = None,
                 is_function: bool = True) -> PowangAny
    def call_function(self, function: PowangFunction,
                      arguments: list[PowangAny],
                      where: str = "function call") -> PowangAny

def run_program(source: str, *, path: str | Path, check: bool = True,
                state=None, trace: bool = False,
                engine_options: VMRunOptions | None = None) -> PowangAny
```

`call_function` is the single entry for calling a VM compiled function from
the interpreter and from the tree walker bridge. It performs argument binding
through `src.vm.dispatch.bind_arguments`, runs the code object and applies the
return cast and copy.

## 10. Scope bridging invariant

While a VM frame executes, these invariants hold:

- `state.scope.variables[-1]` is the frame `LocalStore`.
- `state.scope.functions[-1]` is the frame function table.
- `state.scope.ObjectTypes[-1]` is the frame type table.
- `state.scope.wildcard_sources[-1]` is the frame wildcard table.
- `state.call_frames` contains one `Frame` per active VM call with the function
  name and current source position.

The interpreter pushes and pops these exactly once per frame, including on
error unwind. This lets shared runtime helpers such as
`getUndefinedVariable`, `assignWithChecks`, `evaluate_instantiation`,
`_match_pattern`, `call_native_method` and the builtin table operate on VM
frames without changes.

VM function values carry three additional attributes:

- `code`: the `CodeObject` to execute.
- `vm_image`: the owning `ProgramImage`.
- `vm_name`: the display name.

When `callFunction` in `src.runtime` sees a function with `code` and the active
state engine is `vm`, it delegates to `VM.call_function`.

## 11. Engine selection

`InterpreterState` gains `engine: str = "vm"`. Accepted values are `tree`
and `vm`. Precedence:

1. `--engine=tree` or `--engine=vm` on the command line.
2. `POWANG_ENGINE` environment variable.
3. `project.engine` from a loaded `Project` value.
4. Default `vm`.

The module loader evaluates imported modules with the active engine. In `vm`
mode a module body is compiled and executed by the VM, then exported with the
same export rules as `evaluate_module_ast`. When the optional bytecode cache is
enabled, imported module images are cached with their source and transitive
dependency hashes.

## 12. CLI

`powang vm disasm <file.po> [--json] [--no-verify]` compiles and prints tables.
`powang vm run [--trace] <file.po> [args...]` runs with the VM engine.
`powang vm diff <file.po>` runs both engines and reports mismatches.
`powang vm bench [--runs N] [dir]` runs the benchmark corpus.
`powang --engine=vm file.po` runs a file with the VM engine.

Exit codes match the main CLI: 0 success, 1 language error, 2 usage error,
3 internal error, 130 interrupt.
