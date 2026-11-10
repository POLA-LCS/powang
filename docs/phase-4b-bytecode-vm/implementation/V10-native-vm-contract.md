# V10: Native ABI and Runtime Limits

Purpose: close the remaining design gaps after V9. This phase defines the native VM contract, records the host memory and async model, and explains why a JIT, a Python garbage collector and coroutine suspension are not part of the Python reference VM.

## Objective

The Python reference VM is complete and is the differential oracle. This phase makes the contract that a native VM consumes explicit and machine readable, so a native implementation cannot drift from the opcode numbering, value tags, operand widths or image format. It also records the runtime boundaries that the design deliberately keeps out of the Python implementation.

This phase does not implement a production native VM. The design assigns the native VM to a separate implementation effort. This phase delivers the contract that effort starts from.

## Prerequisites

- V9 is `gate green` for the opt-in release.
- The Python reference VM passes the full suite on both engines.
- The example corpus and the differential corpus report zero mismatches.
- `src/vm/opcodes.py`, `src/vm/image.py` and `src/vm/values.py` are the single source of the ABI.

## Deliverables

### By file

| File | Work |
|---|---|
| `src/vm/native_abi.py` | `abi_document`, `tag_table`, `render_json_contract`, `render_c_header` |
| `src/vm/cli.py` | `powang vm abi` and `powang vm abi --json` |
| `tests/test_vm_tooling.py` | ABI header shape, tag count, opcode count, CLI output |
| `docs/phase-4b-bytecode-vm/implementation/V10-native-vm-contract.md` | This contract |

### Native contract

The native VM consumes one `PWB1` image. The stable parts are:

- Magic bytes `PWB1`, format version `1`, language version `0.22.0`, CRC32 checksum.
- One opcode byte per instruction, followed by fixed width little endian operands.
- The opcode number, name, operand layout, operand widths and stack effect are generated from `src/vm/opcodes.py`.
- The value tag order is fixed at `nova`, `undef`, `bool`, `int`, `num`, `char`, `str`, `arr`, `tup`, `map`, `set`, `fun`, `obj`, `module`, `task`, `error`, `ref`, `handle`, `project`, `any`.
- The image tables are modules, types, traits, functions, constants, call sites, patterns, type specs, sources, global names, strings, debug lines and code objects.
- A code object carries its own constant pool, source span table, exception table, local names, parameter names and flags.
- The C header is generated with `powang vm abi`. The JSON contract is generated with `powang vm abi --json`.

A native VM must pass the same conformance corpus as the Python VM. The corpus is the example suite plus the differential inline corpus. The native VM is ready for the default switch only after the same V9 gates pass.

### Runtime limits

The Python reference VM uses the host Python allocator and garbage collector. It does not implement a separate collector. This is a deliberate design choice for the reference engine. A native VM must choose a traced or reference counted heap and document it in its own ADR.

The async model uses lazy tasks and worker tasks. It does not suspend a coroutine at an arbitrary expression boundary. `AWAIT` runs a lazy task on the current thread or waits for a worker task. Preemptive scheduling and coroutine suspension would need a new bytecode version and a new task state machine, so they remain out of scope.

The Python VM does not include a JIT. A JIT can be added behind the same verifier, bytecode contract and differential suite. It must preserve source spans for debugging or keep a separate debug image.

### Native ABI header

`powang vm abi` prints a C header with:

- `PWB_FORMAT_VERSION` and `PWB_LANGUAGE_VERSION`.
- `PwbOpcode` with one enum member per opcode.
- `PwbTag` with one enum member per value tag.
- `PwbOperandKind` with the operand kind values.
- `PwbOpcodeInfo` and `PWB_OPCODE_COUNT`.

`powang vm abi --json` prints the same data as a deterministic JSON document with the full opcode table, operand widths and stack effects.

## Acceptance criteria

- The generated header names every registered opcode and every canonical tag.
- The generated JSON parses and reports the format version, language version, opcode count and tag count.
- The ABI generator reads only the Python registry and image constants, never a hand maintained second table.
- A change to an opcode name, number, operand or stack effect changes the generated header and JSON in the same commit.
- The Python VM and the tree walker still report zero mismatches.

## Verification commands

```powershell
.\.venv\Scripts\python.exe powang.py vm abi
.\.venv\Scripts\python.exe powang.py vm abi --json
.\.venv\Scripts\python.exe -m unittest tests.test_vm_tooling -v
```

## Atomic commit plan

- `vm(abi): generate the native opcode and tag contract`
- `docs(phase-4b): record the native ABI and runtime limits`

## Risks and rollback

- A native VM that hand copies the opcode table will drift. The generator is the mitigation.
- A native heap that changes copy semantics will fail the differential corpus. The copy rules stay in the Python reference and in the contract.
- A JIT that removes source spans will break the debugger. Keep a debug image.

## Exit gate

- The ABI generator is covered by tests.
- The generated header and JSON are deterministic.
- The native contract is documented.
- The Python reference VM remains the differential oracle.
