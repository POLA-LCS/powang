# V0: Contracts and Scaffold

Purpose: create the bytecode VM package skeleton, the single opcode registry, the program image codec, the builder, the verifier skeleton, the disassembler skeleton, the engine flag and the differential harness.

## Objective

At the end of V0 the repository contains a working but intentionally small bytecode pipeline. A trivial program made of numeric literals and arithmetic operators compiles to a `ProgramImage`, passes verification, serializes and deserializes without loss, disassembles to stable text, and runs on both the tree walker and the VM with identical output. No existing test changes behavior.

The phase also freezes the interfaces that every later phase uses. The opcode registry, the image dataclasses, the builder API, the verifier entry points, the frame primitives and the engine selection rules are contract surfaces. Later phases add handlers and lowering rules. They do not rename these surfaces.

Semantic reference: `docs/phase-4b-bytecode-vm/01-architecture-and-execution.md`, `docs/phase-4b-bytecode-vm/03-bytecode-format-and-opcodes.md` and `docs/phase-4b-bytecode-vm/06-tooling-testing-and-performance.md`.

## Prerequisites

- The design set under `docs/phase-4b-bytecode-vm/` is complete.
- `docs/phase-4b-bytecode-vm/implementation/00-contracts.md` is the binding interface contract.
- The baseline suite is green before the first commit:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

- The working tree is clean. V0 must not change any existing test file.
- Python 3.12 or newer is available through `.\.venv\Scripts\python.exe`.

## Deliverables

### By file

| File | Work in V0 |
|---|---|
| `src/vm/__init__.py` | Package exports, `ENGINE_TREE`, `ENGINE_VM`, `SUPPORTED_ENGINES`, `LANGUAGE_VERSION` re-export |
| `src/vm/opcodes.py` | `WIDTHS`, `Operand`, `OpcodeSpec`, `OPCODES`, `BY_NAME`, `BY_OPCODE`, `spec`, `encode_operands`, `decode_operands`, `decode_instruction` |
| `src/vm/image.py` | `SourceSpan`, `ExceptionEntry`, `Constant`, `CodeObject`, `CallSite`, `PatternDescriptor`, `TypeInfo`, `TraitInfo`, `FunctionInfo`, `ModuleInfo`, `ProgramImage`, binary codec, `read_image`, `write_image` |
| `src/vm/builder.py` | `Label`, `Builder`, operand validation, label placement and patching, constant and span deduplication, `finish` |
| `src/vm/verifier.py` | `VerificationError`, `verify_code`, `verify_image`, decode loop, stack simulation, metadata range checks |
| `src/vm/values.py` | `TAGS`, `tag_of`, `truthy`, `is_nova`, `is_defined`, `is_weak`, `nova`, `copy_value` for scalars, `unwrap`, constant conversion, `stable_key`, `encode_constant_json`, `decode_constant_json`, `SpreadValue`, `spread_values` |
| `src/vm/frames.py` | `LocalStore`, `HandlerEntry`, `VMFrame`, stack helpers, handler stack helpers |
| `src/vm/compiler.py` | `CompileError`, `compile_ast`, `compile_source`, literal, binary and unary arithmetic lowering, module init code object |
| `src/vm/interpreter.py` | `VMRunOptions`, `VM`, `run_program`, dispatch loop, handlers for V0 opcodes only |
| `src/vm/host.py` | Narrow builtin shim for `print` and `println` only, with a documented V0 scope |
| `src/vm/errors.py` | `raise_vm_error`, `with_span`, `format_error`, source position helpers |
| `src/vm/disasm.py` | `disassemble_code`, `disassemble_image`, instruction offsets, span column, table rendering |
| `src/vm/trace.py` | `TraceEvent`, `TraceSink`, `TextTraceSink`, no-op sink |
| `src/vm/differential.py` | `run_pair`, `DiffResult`, corpus runner, `python -m src.vm.differential` entry point |
| `src/vm/cli.py` | `python -m src.vm.cli` with `run`, `disasm` and `diff`, plus the `powang vm` dispatch hook |
| `src/vm/tests/__init__.py` | Test package marker |
| `src/vm/tests/test_opcodes.py` | Registry order, operand widths, encode and decode round trip, reject cases |
| `src/vm/tests/test_image.py` | Image round trip, CRC rejection, constant JSON determinism, empty image |
| `src/vm/tests/test_builder.py` | Label patch, unplaced label error, duplicate label error, constant and span deduplication |
| `src/vm/tests/test_verifier.py` | Truncated instruction, invalid constant, invalid slot, jump out of range, stack underflow, merge mismatch |
| `src/vm/tests/test_disasm.py` | Header, table rendering, instruction offsets, span column |
| `src/vm/tests/test_golden_disasm.py` | Golden snapshot comparison and `POWANG_UPDATE_GOLDEN` update path |
| `src/vm/tests/test_differential.py` | Harness comparison fields and mismatch reporting |
| `src/vm/tests/golden/` | Golden disassembly snapshots for V0 |
| `src/vm/tests/corpus/v0/` | Differential corpus for V0 |
| `tests/test_vm_engine.py` | Engine flag routing and no regression in existing behavior |

Existing files that V0 touches:

| File | Change |
|---|---|
| `src/state.py` | Add `engine: str = "tree"` to `InterpreterState` |
| `powang.py` | Parse `--engine=tree` and `--engine=vm`, add the `vm` subcommand dispatch, keep the existing default |
| `src/runtime.py` | Add a narrow `callFunction` delegation hook for functions that carry a VM `code` attribute, inactive while `state.engine == "tree"` |

### By language feature

| Feature | V0 coverage |
|---|---|
| Integer literal | `LOAD_INT` for signed 64 bit values, `LOAD_BIGINT` for larger values |
| Floating literal | `LOAD_NUM` |
| `nova` literal | `LOAD_NOVA` |
| Boolean literal | `LOAD_TRUE` and `LOAD_FALSE` |
| Arithmetic expression | `ADD`, `SUB`, `MUL`, `DIV`, `MOD`, `NEG` |
| Parenthesized expression | No instruction, evaluation order preserved |
| Top level statement | Module init code object ending in `LOAD_NOVA`, `RETURN` |
| Output for differential tests | `CALL_BUILTIN` with the `print` and `println` builtin IDs only |
| Engine selection | `--engine=tree`, `--engine=vm`, `POWANG_ENGINE`, project metadata engine key, default `tree` |

## Task checklist

- [ ] Add `src/vm/__init__.py` with engine constants, supported engine set and package exports.
- [ ] Add `src/vm/opcodes.py` with the full fixed opcode registry, operand widths and encode and decode functions.
- [ ] Add `src/vm/image.py` with image dataclasses, deterministic constant JSON and the binary codec.
- [ ] Add `src/vm/builder.py` with labels, operand validation, constant pooling and span deduplication.
- [ ] Add `src/vm/values.py` and `src/vm/frames.py` with value helpers and frame primitives.
- [ ] Add `src/vm/verifier.py` with decode, stack simulation and metadata reject rules.
- [ ] Add `src/vm/compiler.py` and `src/vm/interpreter.py` for literals, arithmetic, module init and the V0 builtin shim.
- [ ] Add `src/vm/disasm.py`, `src/vm/trace.py` and `src/vm/errors.py` with stable offsets and source span rendering.
- [ ] Add `src/vm/differential.py` and `src/vm/cli.py` with `run`, `disasm`, `diff` and the corpus runner.
- [ ] Add `src/state.py` engine field and `powang.py` engine flag and `vm` subcommand routing.
- [ ] Add `src/vm/tests/` unit tests, `tests/test_vm_engine.py` and the V0 corpus and golden snapshots.

## Lowering table

| Source construct | Emitted instruction sequence |
|---|---|
| `123` | `LOAD_INT 123` |
| `9223372036854775808` | `LOAD_BIGINT const_index` |
| `1.5` | `LOAD_NUM 1.5` |
| `nova` | `LOAD_NOVA` |
| `true` | `LOAD_TRUE` |
| `false` | `LOAD_FALSE` |
| `1 + 2 * 3` | `LOAD_INT 1`, `LOAD_INT 2`, `LOAD_INT 3`, `MUL`, `ADD` |
| `(1 + 2) * 3` | `LOAD_INT 1`, `LOAD_INT 2`, `ADD`, `LOAD_INT 3`, `MUL` |
| `-value` | evaluate `value`, then `NEG` |
| `println(value)` | evaluate `value`, then `CALL_BUILTIN call_site` |
| top level program `statement...` | lower each statement, then `LOAD_NOVA`, `RETURN` |

The `CALL_BUILTIN` shim is limited to `print` and `println`. V3 replaces the shim with the full builtin table from `src.builtins.builtins.BUILTINS`. The shim must use the same arity rule and the same function object as the tree walker.

## Runtime semantics notes

### Package and value model

- The package root is `src/vm`.
- Runtime values are the existing `PowangAny` classes from `src.powang_types`. V0 must not create a second value model.
- Language errors are `PowangError` instances from `src.error`. The VM never invents a parallel error type.
- `src/vm/__init__.py` exports `ENGINE_TREE = "tree"`, `ENGINE_VM = "vm"`, `SUPPORTED_ENGINES = frozenset({"tree", "vm"})` and the image format constants.

### Opcode registry

- `OPCODES` is a tuple ordered by opcode number. Opcode numbers start at 0 and are assigned in registry order.
- Appending an opcode at the end is allowed. Reordering or renumbering requires a format version bump.
- `OpcodeSpec.size` is `1 + sum(WIDTHS[operand.width] for operand in operands)`.
- `encode_operands` validates operand count, integer width, signed range and `f64` type before packing.
- `decode_instruction` returns `(spec, operand_dict, next_offset)` and raises `ValueError` on an unknown opcode or truncated operand.
- The full V0 registry is the fixed list below. Every later phase implements its slice of this list and adds no duplicate declaration.

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

### Program image

- `FORMAT_MAGIC = b"PWB1"` and `FORMAT_VERSION = 1`.
- `LANGUAGE_VERSION` starts at `"0.20.0"` for the implementation train. V9 changes the value to `"0.21.0"` in the release commit.
- Every table is little endian.
- The header layout is magic, u16 format version, u16 flags, u16 length plus UTF-8 language version, u32 table count, then each table as u32 byte length plus bytes, then u32 CRC32 of everything before the checksum.
- Strings are u32 length plus UTF-8 bytes.
- Constants are a u8 kind tag plus a kind specific body. AST and descriptor constants use deterministic JSON from `values.encode_constant_json`.
- Code bytecode is u32 length plus raw bytes. `span_table` is one u32 per instruction. Exception entries are fixed records.
- `ProgramImage.code`, `constant`, `call_site`, `pattern`, `type_info`, `trait_info`, `function_info` and `module_info` validate the index and return the entry.
- `to_bytes` and `from_bytes` round trip byte for byte for an unchanged image.
- A bad magic, a bad CRC or a table length past the end raises `ValueError` with a stable message.

### Builder

- `Builder.emit` validates the opcode name, operand count, operand width and integer range at emit time.
- `Builder.emit_label`, `new_label`, `place` and `patch` implement label based jumps. `patch` is idempotent.
- `finish` raises `ValueError` on an unplaced label, a jump operand that names no label, or a label placed twice.
- `new_constant` deduplicates by `(kind, stable_key(value))`. Constants are pooled per code object.
- `add_span` deduplicates identical `SourceSpan` values.
- `declare_local` and `reserve_local` assign slots in declaration order. `set_parameter_names` sets the parameter name table.
- `finish` computes `local_count`, `max_stack` and `max_frame_depth` when the caller does not supply them.

### Verifier

- `verify_code(code, image=None, strict=True)` decodes every instruction once and records instruction boundaries.
- The verifier simulates stack height. It rejects underflow, a merge point with two different heights, and a fallthrough past the last instruction.
- The verifier rejects unknown opcodes, truncated instructions, an out of range constant index, a slot at or above `local_count`, a jump outside the code object, a jump into the middle of an instruction, a negative count, a bad exception range, a non empty `span_table` with the wrong length, and a return spec index outside the type spec table when an image is present.
- `verify_image` verifies every code object and every cross table reference, including call site and pattern indices when present.
- The verifier never executes user code and never follows a call into another code object.

### Frames and values

- `LocalStore` is a name view over a contiguous slot array. It implements `MutableMapping[str, PowangAny]` and behaves like the dictionary used for `ScopeStack.variables`.
- `VMFrame` owns `stack`, `ip`, `handlers` and `span_index`. `push`, `pop`, `peek` and `require_stack` are the only stack primitives.
- `values.truthy` uses `PowangBoolean.cast(value).data`, which is the same rule the tree walker uses for `if` and `loop if`.
- `values.copy_value` handles scalars in V0. V3 extends it to containers and objects with copy on write.
- `values.stable_key` must be deterministic across runs. AST nodes and type nodes are keyed by JSON with token enums rendered by their fully qualified enum name.

### Engine selection and bridging

- `InterpreterState.engine` defaults to `"tree"`.
- Precedence is command line, then `POWANG_ENGINE`, then the project metadata engine key, then `"tree"`.
- Accepted values are `tree` and `vm`. Any other value is a usage error with exit code 2.
- While a VM frame executes, these invariants hold: `state.scope.variables[-1]` is the frame `LocalStore`, `state.scope.functions[-1]` is the frame function table, `state.scope.ObjectTypes[-1]` is the frame type table, `state.scope.wildcard_sources[-1]` is the frame wildcard table, and `state.call_frames` contains one `Frame` per active VM call.
- The interpreter pushes and pops these exactly once per frame, including on error unwind.
- `src.runtime.callFunction` delegates to `VM.call_function` only when the callee carries a `code` attribute and `state.engine == "vm"`. The tree path is unchanged.

### Differential harness

- `run_pair(source, path, options)` runs the tree walker and the VM in fresh states.
- `DiffResult` stores `tree_stdout`, `vm_stdout`, `tree_stderr`, `vm_stderr`, `tree_exit`, `vm_exit`, `tree_files`, `vm_files`, `match` and `reason`.
- The harness compares standard output, standard error, exit code and created or modified files. Timing is recorded for reports only.
- A mismatch prints the source path, the first differing field, both values and the disassembly of the VM image.
- `--fail-fast` stops at the first mismatch. Without it the runner reports every mismatch and exits 1 when any mismatch exists.

## Acceptance criteria

1. `OPCODES` contains every name in the fixed registry list exactly once and opcode numbers are contiguous from 0.
2. Every `OpcodeSpec.size` matches `1 + sum(WIDTHS[operand.width])` and every operand kind is one of the documented kinds.
3. Encoding and decoding every opcode with in range operands round trips to the same bytes and the same operand dictionary.
4. Encoding an out of range operand, a wrong operand count or a wrong operand type raises `ValueError` before any byte is written.
5. `ProgramImage.to_bytes` then `from_bytes` reproduces an equal image and byte identical output for a second serialization.
6. Flipping one byte in a serialized image raises `ValueError` for the checksum.
7. `Builder.finish` produces a jump target that lands on the first instruction after the label, and an unplaced label raises `ValueError`.
8. `verify_code` rejects each reject case in `src/vm/tests/test_verifier.py` with `VerificationError` and accepts every code object produced by the V0 compiler.
9. `disassemble_image` prints the magic, format version, language version, module table, code table, constant pool, instruction offsets and source span for every instruction.
10. `.\.venv\Scripts\python.exe powang.py --engine=vm src\vm\tests\corpus\v0\arith_basic.po` produces the same stdout and exit code as `--engine=tree`.
11. The existing test suite is green and `git diff --name-only tests` reports no changed existing test file.
12. The differential runner reports zero mismatches for `src\vm\tests\corpus\v0`.

## Verification commands

```powershell
.\.venv\Scripts\python.exe -c "from src.vm.opcodes import OPCODES; assert [s.opcode for s in OPCODES] == list(range(len(OPCODES))); assert len({s.name for s in OPCODES}) == len(OPCODES); print(len(OPCODES))"
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_opcodes -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_image -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_builder -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_verifier -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_disasm -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_golden_disasm -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_differential -v
.\.venv\Scripts\python.exe -m unittest discover -s src\vm\tests -t . -p "test_*.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
.\.venv\Scripts\python.exe -m src.vm.differential --corpus src\vm\tests\corpus\v0 --fail-fast
.\.venv\Scripts\python.exe powang.py --engine=tree src\vm\tests\corpus\v0\arith_basic.po
.\.venv\Scripts\python.exe powang.py --engine=vm src\vm\tests\corpus\v0\arith_basic.po
.\.venv\Scripts\python.exe powang.py vm disasm src\vm\tests\corpus\v0\arith_basic.po
.\.venv\Scripts\python.exe powang.py vm diff src\vm\tests\corpus\v0\arith_basic.po
git diff --name-only -- tests
```

Update the golden snapshots only after a reviewed lowering change:

```powershell
$env:POWANG_UPDATE_GOLDEN = "1"
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_golden_disasm -v
Remove-Item Env:\POWANG_UPDATE_GOLDEN
```

## Differential test corpus

Create these files under `src/vm/tests/corpus/v0/`.

`arith_basic.po`:

```po
println(1 + 2 * 3);
println((1 + 2) * 3);
println(7 / 2);
println(2 - 5);
println(-(3 * 4));
```

`arith_precedence.po`:

```po
println(10 - 4 - 3);
println(2 * 3 + 4 * 5);
println(100 / 10 / 2);
println(7 % 4);
```

`literals.po`:

```po
println(nova);
println(true);
println(false);
println(123);
println(1.5);
```

`mixed_arith.po`:

```po
println(1 + 2.5);
println(3 * 2.0);
println(1 / 0);
```

The expected tree walker output is the source of truth. Do not hand write expected output in the harness. The harness runs `--engine=tree` and records the result, then runs `--engine=vm` and compares.

## Golden disassembly cases

| Case | Source | Required assertions |
|---|---|---|
| `v0_arith_basic` | `src/vm/tests/corpus/v0/arith_basic.po` | Header magic, format version, language version, code name, `LOAD_INT`, `MUL`, `ADD`, `CALL_BUILTIN`, `RETURN`, monotonic offsets |
| `v0_literals` | `src/vm/tests/corpus/v0/literals.po` | `LOAD_NOVA`, `LOAD_TRUE`, `LOAD_FALSE`, `LOAD_INT`, `LOAD_NUM`, constant pool entries, span lines |
| `v0_arith_precedence` | `src/vm/tests/corpus/v0/arith_precedence.po` | Left associativity, `MOD` presence, no hidden temporary instructions |
| `v0_empty_image` | synthetic empty image | Empty module table, empty code table, valid checksum |

Golden files live under `src/vm/tests/golden/` with the suffix `.disasm`. A snapshot contains the full `disassemble_image` output, normalized to LF line endings. The test compares exact text. Any change requires a reviewed opcode or lowering change and a note in the commit message.

## Atomic commit plan

1. `vm(v0): add vm package skeleton and engine constants`
2. `vm(v0): add opcode registry and operand codec`
3. `vm(v0): add program image dataclasses and binary codec`
4. `vm(v0): add instruction builder and label resolution`
5. `vm(v0): add value helpers and frame primitives`
6. `vm(v0): add verifier skeleton and reject rules`
7. `vm(v0): add minimal compiler and interpreter for literals and arithmetic`
8. `vm(v0): add disassembler trace sinks and error helpers`
9. `vm(v0): add engine selection flag and vm cli subcommands`
10. `vm(v0): add differential harness and v0 corpus`
11. `vm(v0): add v0 unit tests and golden disassembly snapshots`

## Risks and rollback

| Risk | Mitigation | Rollback |
|---|---|---|
| Opcode numbering churn breaks snapshots | Freeze the registry order in V0 and append only | Revert the opcode commit and regenerate snapshots from the previous registry |
| Image codec becomes nondeterministic | Sort nothing that has semantic order, use `stable_key` for deduplication, test byte equality | Revert the image commit. Images are not yet persisted in the repository |
| Builder label patching emits wrong offsets | Test forward and backward jumps, test idempotent `patch`, compare offsets in golden files | Revert the builder commit. Compiler V0 depends only on forward labels |
| Engine flag changes tree behavior | The flag defaults to `tree` and the tree path is untouched. `tests/test_vm_engine.py` asserts tree output before and after | Revert the `powang.py` and `src/state.py` commit |
| Verifier rejects valid V0 code | Keep the V0 verifier strict but small. Add a test that verifies every V0 corpus image | Disable strict merges for the failing opcode family with a documented TODO, then fix in V1 |
| Builtin shim drifts from the tree walker | Import the `print` and `println` callables from `src.builtins.builtins.BUILTINS` and use the same arity rule | Revert the host shim commit. V0 output tests then fail and V0 cannot close |

## Exit gate

V0 is closed when all of these are true:

- [ ] The full opcode registry exists once and opcode numbers are contiguous.
- [ ] Encoding, decoding and image round trip tests pass.
- [ ] The verifier rejects the documented malformed cases and accepts every V0 code object.
- [ ] The disassembler renders every V0 image table and instruction offset.
- [ ] `--engine=vm` runs the V0 corpus with output identical to `--engine=tree`.
- [ ] The differential runner reports zero mismatches for `src\vm\tests\corpus\v0`.
- [ ] The existing suite is green and no existing test file changed.
- [ ] The tree walker remains the default engine.
