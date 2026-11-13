# V10: Native ABI and Runtime Limits

Purpose: close the remaining design gaps after V9. This phase defines the native VM contract, records the host memory and async model, and explains why a JIT, a Python garbage collector and coroutine suspension are not part of the Python reference VM.

## Objective

The Python reference VM is complete and is the differential oracle. This phase makes the contract that a native VM consumes explicit and machine readable, so a native implementation cannot drift from the opcode numbering, value tags, operand widths or image format. It also records the runtime boundaries that the design deliberately keeps out of the Python implementation.

N0 to N6 implement the opt-in native VM under `native/`. The Python VM remains the default engine and the differential oracle. The native engine is selected with `--engine=native` or `powang vm native run`.

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

The native implementation lives in `native/` and `src/vm/native/`. The files above define the ABI and the tooling that the implementation consumes.

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

### Implemented native runtime

The implemented runtime consumes the contract above and adds these boundaries:

- `native/include/pwb/` holds the value, object, image, metadata, error, host, task, file and reference declarations. `native/src/vm.cpp` holds the interpreter and the module, task and host integration.
- `run_embedded_image`, `run_embedded_image_with_meta` and `run_embedded_bundle_with_meta` are the entry points. The `PWBB` bundle carries the entry image, module graph, project block and SHA-256 digest. `PWBM` version 2 carries function and type descriptors.
- The runtime uses an arena for one run. `copy_value` implements the Python VM value copy rules, including a cycle memo for containers and objects. There is no tracing collector and no reference counting in the current implementation.
- Language errors are `ErrorObject` values carried by `UnwindSignal` across recursive `execute` calls. The error kind, where, message, details, line, column, frames and cause follow the Python text contract.
- References carry a target kind, a frame lifetime token and a target type. A stale frame reference reports the Python reference error.
- Tasks are deterministic. A spawned worker runs on the spawning thread against a cloned module snapshot. There is no true thread pool and no coroutine suspension.
- `Host::call_extern` is the host bridge. `StdoutHost` implements `math`, `strings`, `json`, `url`, `crypto`, `time`, `env`, `log` and script arguments. `HostCallError` becomes a catchable `[EXTERN ERROR]`. HTTP modules and the generic host callback bridge are not implemented.
- `--engine=native` routes a file, project or check-only run to the native engine. The warm executable cache is keyed by the generated source and the runtime library timestamp.

### Default engine decision at the native milestone

The package version is `0.25.0`. The image language version remains `0.22.0` because the image contract did not change.

The Python VM remains the default engine at the native milestone. The native engine is opt in. The full parity gates pass, but the HTTP host modules, the generic host callback bridge and true parallel worker execution are not implemented. Flipping the default would change behavior for programs that use those host modules. The flip condition is a complete host surface and a green full parity sweep after the flip.

### Runtime limits

The Python reference VM uses the host Python allocator and garbage collector. It does not implement a separate collector. This is a deliberate design choice for the reference engine. The native runtime uses an arena for the lifetime of one run and copies values with `copy_value`. A future traced or reference counted heap must preserve the value copy rules and pass the same differential corpus.

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
.\.venv\Scripts\python.exe -m src.vm.native.differential --examples examples --json
.\.venv\Scripts\python.exe -m src.vm.native.differential --fuzz --seed 7 --count 1000 --json
.\.venv\Scripts\python.exe -m src.vm.native.differential --fuzz --seed 2026 --count 1000 --json
.\.venv\Scripts\python.exe -m unittest tests.test_native_access_control tests.test_native_stdlib tests.test_native_bench -v
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
- The native engine passes the full Python VM suite, the full tree walker suite, every example, the native corpora, the seeded fuzz gates, the stress gate and the benchmark gate.
- The native engine remains opt in until the HTTP host modules, the generic host callback bridge and true parallel worker execution are complete.
