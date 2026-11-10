# V4: User Types, Enums and Operator Overloading

Purpose: deliver type declarations, constructors, fields, access control, instance and static methods, object copy semantics, enums, operator traits, comparison dispatch, const and element locks, safe member access, coalesce and object and enum match patterns on the bytecode VM.

## Objective

At the end of V4 the VM executes user defined object types. A type declaration registers a type object with a field layout and a method table. Construction binds fields in declaration order, applies defaults and runs the constructor body with `this`. Field reads and writes use resolved field IDs with access control. Instance methods, static methods and operator trait methods call through the existing tree walker dispatch helpers.

Enums become first class values with the same display text and equality rules as the tree walker. Operator overloading works through the existing `performOperation` dispatch path, so arithmetic and comparison on user objects need no VM specific operator table.

Object values copy through `PowangCopyConstructObjectType`, which is the existing copy constructor behavior. A copied object can be mutated without changing the original, including when its fields hold containers.

V4 also completes `match` with object patterns, enum patterns and expression position match, and adds safe member access `?.` and coalesce `??`.

Semantic reference: `docs/phase-4b-bytecode-vm/02-values-heap-and-frames.md` sections 8.5 to 8.7, 9.6 and 9.7, `docs/phase-4b-bytecode-vm/04-compiler-lowering.md` sections 12.9, 12.10 and 12.11, and `docs/phase-4b-bytecode-vm/05-runtime-semantics-and-debugging.md` sections 13.3 and 13.4.

## Prerequisites

- V3 is `gate green`. Containers, strings, native methods and sequence patterns work.
- The V3 corpus reports zero mismatches:

```powershell
.\.venv\Scripts\python.exe -m src.vm.differential --corpus src\vm\tests\corpus\v3 --fail-fast
```

- The baseline suite is green.

Contract surfaces this phase depends on:

- `src/vm/image.py`: `TypeInfo`, `CallSite` dispatch values `method`, `static`, `operator` and `construct`, field descriptor constants.
- `src/vm/declarations.py`: type and object runtime entry points.
- `src/vm/dispatch.py`: method dispatch and operator dispatch.
- `src/vm/values.py`: `copy_value`, `ensure_unique`, `tag_of`, constant conversion.
- `src/runtime.py`: `performOperation`, `performUnaryOperation`, `callMethod`, `callTraitMethod`, `_call_operator_method`, `_private_access_allowed`, `PowangCopyConstructObjectType`, `PowangCopyConstruct`, `assignWithChecks`, `getUndefinedVariable`.

## Deliverables

### By file

| File | Work in V4 |
|---|---|
| `src/vm/compiler.py` | Type and enum declarations, constructor code objects, method code objects, field access, member access, static and instance calls, operator calls, enum member loads, locks, safe access, coalesce, object and enum match, expression match |
| `src/vm/declarations.py` | `declare_type`, `declare_enum`, `construct_object`, `bind_fields`, `copy_object`, `apply_locks`, `find_method`, `find_static_method`, `call_method`, `call_static`, `call_operator` |
| `src/vm/dispatch.py` | Method lookup by concrete type, private access check, operator trait call, comparison dispatch wrapper, ambiguity errors for V5 |
| `src/vm/values.py` | Object copy, field get and set, member get and set, enum equality helpers, lock flag application, type check helpers |
| `src/vm/image.py` | `TypeInfo` population for object and enum kinds, field descriptor constants, method table entries, trait name slots |
| `src/vm/interpreter.py` | Handlers for `DECLARE_TYPE`, `CONSTRUCT`, `NEW_ENUM`, `LOAD_FIELD`, `STORE_FIELD`, `LOAD_MEMBER`, `STORE_MEMBER`, `LOAD_MEMBER_SAFE`, `LOAD_ENUM_MEMBER`, `SET_LOCKS`, `CALL_METHOD`, `CALL_STATIC`, `CALL_OPERATOR`, `MATCH` object and enum patterns |
| `src/vm/tests/test_types.py` | Type declaration, construction, defaults, constructor body, copy |
| `src/vm/tests/test_fields.py` | Field load, store, private access, dynamic member access |
| `src/vm/tests/test_methods.py` | Instance, static, private and operator methods |
| `src/vm/tests/test_enums.py` | Enum declaration, variant load, display, equality |
| `src/vm/tests/test_operator_dispatch.py` | Arithmetic, unary and comparison operator traits |
| `src/vm/tests/test_locks.py` | Const and element locks |
| `src/vm/tests/test_match_objects.py` | Object patterns, enum patterns, guards, expression match |
| `src/vm/tests/golden/` | V4 golden disassembly snapshots |
| `src/vm/tests/corpus/v4/` | V4 differential corpus |
| `tests/test_vm_types.py` | End to end VM engine test for user types |

### By language feature

| Feature | Required behavior |
|---|---|
| Type declaration | `type Point[+]` with fields `x` and `y` registers a type object |
| Field default | `- secret: int = 7;` binds the default at construction |
| Constructor body | `fun constructor { ... }` runs with `this` after field binding |
| Positional construction | `Point.[1, 2]` binds fields in declaration order |
| Named construction | `Point.[x >> 1, y >> 2]` binds by field name |
| Tuple cast construction | `.[1, 2] as Point` calls the constructor |
| Field read | `object.field` through `LOAD_FIELD` |
| Field write | `object.field = value` through `STORE_FIELD` with copy |
| Dynamic member read | `LOAD_MEMBER name` by runtime name |
| Dynamic member write | `STORE_MEMBER name` |
| Safe member read | `object?.field` returns nova when the object is nova |
| Private field | `- field: T` rejected outside the owning type |
| Public and private type access | `[+]` and `[-]` enforced by the checker for static construction |
| Instance method | `fun this.method(...)` through `CALL_METHOD` |
| Static method | `fun method(...)` through `CALL_STATIC` |
| Private method | `- fun this.method(...)` and `- fun method(...)` |
| Operator method | `fun this.add(...)`, `subtract`, `multiply`, `divide`, `remainder`, `negate`, `compare` |
| Operator dispatch | `+`, `-`, `*`, `/`, `%`, unary `-` and comparisons on user objects |
| Explicit operator call | `Add.add(left, right)` through `CALL_OPERATOR` |
| Enum declaration | `type Color enum { RED, GREEN }` |
| Enum variant load | `Color.RED` through `LOAD_ENUM_MEMBER` |
| Enum display and equality | `<Color: RED>` and equality by type and variant |
| Const and element locks | `SET_LOCKS` applies the declared lock flags |
| Copy semantics | Object copies are independent, including container fields |
| Object match | `case Point.[x, y]` and `case Point.[x: px, y: py]` |
| Enum match | `case Color.RED` |
| Expression match | `value match { case ... >> expression }` |
| Coalesce | `left ?? right` evaluates `right` only when `left` is nova |

## Task checklist

- [ ] Add type table entries, field descriptor constants and `DECLARE_TYPE`.
- [ ] Lower type declarations and field defaults.
- [ ] Add `CONSTRUCT` and the field binding path.
- [ ] Add constructor body compilation with `this`.
- [ ] Lower field reads and writes.
- [ ] Add private field and method access checks.
- [ ] Add static and instance method calls.
- [ ] Add object copy through the copy constructor.
- [ ] Add enum declarations and `LOAD_ENUM_MEMBER`.
- [ ] Add object and enum match patterns.
- [ ] Add expression position match.
- [ ] Add operator trait dispatch for arithmetic and unary operators.
- [ ] Add comparison dispatch through the `Compare` trait.
- [ ] Add const and element locks through `SET_LOCKS`.
- [ ] Add safe member access and coalesce.
- [ ] Add V4 unit tests, corpus, golden snapshots and the type engine test.

## Lowering table

| Source construct | Emitted instruction sequence |
|---|---|
| `type Point[+]` with fields `x` and `y` | module init `DECLARE_TYPE type_id`, `STORE_GLOBAL name` |
| `type Color enum { RED, GREEN }` | module init `DECLARE_TYPE type_id`, `STORE_GLOBAL name` |
| `Point.[1, 2]` | `LOAD_INT 1`, `LOAD_INT 2`, `CONSTRUCT type_id, call_site` |
| `Point.[x >> 1, y >> 2]` | evaluate `1`, evaluate `2`, `CONSTRUCT type_id, call_site` with named argument entries |
| `.[1, 2] as Point` | `LOAD_INT 1`, `LOAD_INT 2`, `MAKE_TUPLE 2`, `CAST Point_spec` |
| `object.field` | evaluate `object`, `LOAD_FIELD field_const` |
| `object.field = value` | evaluate `object`, evaluate `value`, `STORE_FIELD field_const` |
| `this.field` | `LOAD_THIS`, `LOAD_FIELD field_const` |
| `object.method(args)` | evaluate `object`, evaluate args, `CALL_METHOD call_site` |
| `Type.method(args)` | evaluate args, `CALL_STATIC call_site` |
| `this.method(args)` | `LOAD_THIS`, evaluate args, `CALL_METHOD call_site` |
| `Trait.method(object, args)` | evaluate `object`, evaluate args, `CALL_OPERATOR` or `CALL_TRAIT` when the trait is a user trait |
| `left + right` | evaluate `left`, evaluate `right`, `ADD`. The handler dispatches `Add` |
| `left - right` | evaluate `left`, evaluate `right`, `SUB`. The handler dispatches `Subtract` |
| `left * right` | evaluate `left`, evaluate `right`, `MUL`. The handler dispatches `Multiply` |
| `left / right` | evaluate `left`, evaluate `right`, `DIV`. The handler dispatches `Divide` |
| `left % right` | evaluate `left`, evaluate `right`, `MOD`. The handler dispatches `Remainder` |
| `-value` | evaluate `value`, `NEG`. The handler dispatches `Negate` |
| `left < right` | evaluate `left`, evaluate `right`, `LT`. The handler dispatches `Compare` |
| `Color.RED` | `LOAD_ENUM_MEMBER enum_id, variant_id` |
| `value as Point` | evaluate `value`, `CAST Point_spec` |
| `object?.field` | evaluate `object`, `LOAD_MEMBER_SAFE name_const` |
| `object?.method(args)` | evaluate `object`, `DUP`, `JUMP_IF_NOVA end`, `POP`, evaluate args, `CALL_METHOD call_site`, `JUMP end2`, place `end`, `POP`, `LOAD_NOVA`, place `end2` |
| `left ?? right` | evaluate `left`, `DUP`, `JUMP_IF_NOT_NOVA end`, `POP`, evaluate `right`, place `end` |
| `match subject { case Point.[x, y] >> body }` | evaluate `subject`, `STORE_LOCAL subject_slot`, `LOAD_LOCAL subject_slot`, `MATCH pattern, fail`, body |
| `case Color.RED >> body` | `MATCH enum_pattern, fail` |
| `value match { case pattern >> expr }` | `LOAD_NOVA`, `STORE_LOCAL result_slot`, per case `LOAD_LOCAL subject_slot`, `MATCH pattern, fail`, evaluate `expr`, `STORE_LOCAL result_slot`, `JUMP end`, place fail, place end, `LOAD_LOCAL result_slot` |

`SET_LOCKS` is emitted after `CONSTRUCT` when the declared type expression carries const or element locks. The flags use the same bits as V1.

## Runtime semantics notes

### Type table

A type table entry carries:

- `name`: the declared type name.
- `kind`: `object` or `enum`.
- `type_parameters`: generic parameter names, used by V5 constraints.
- `properties`: one tuple per field: `(is_private, name, field_constant_index, type_spec_name)`.
- `methods`: one tuple per method: `(is_static, name, code_index, trait_name, is_private)`.
- `variants`: enum variant names in declaration order.

The field constant at `field_constant_index` is a `Constant(kind="descriptor")` with this JSON shape:

```json
{
  "kind": "field",
  "type": "Point",
  "name": "x",
  "private": false,
  "const": false,
  "default": null
}
```

`default` is `null` or a small JSON value for a constant default. A non constant default expression is compiled into a default code object and stored as `{"kind": "default_code", "index": 7}`. A field default descriptor is evaluated at construction time when the tree walker fills the field. The differential corpus covers private field defaults and the current public field behavior, which the tree walker remains the oracle for.

`DECLARE_TYPE type_id` does the following:

1. Build a `PowangObjectType` with the tree walker shape.
2. Set `type_name` to the declared name.
3. Set `is_enum` for enum kinds.
4. Register the type in `state.scope.ObjectTypes[-1]` under its name.
5. For an enum, create the variant instances and a `PowangMap` of variant name to instance, then store the map in `state.scope.variables[-1]` under the type name.
6. For an object type, push the type object so the following `STORE_GLOBAL` binds the name.

### Construction

`CONSTRUCT type_id, call_site` performs:

1. Read the target `TypeInfo`.
2. Evaluate the call site arguments. They are already on the operand stack.
3. Create a `PowangObjectType` with a field dictionary in declaration order.
4. Bind positional and named arguments to fields by name. Named arguments are evaluated in source order by the call site and mapped here.
5. Fill a missing field from its default descriptor. A missing field without a default raises the same error text as `evaluate_instantiation`:
   - `powang_error_format("TYPE", "(in instantiation)", f"Constructor for '{name}' is missing required argument '{field}'", [f"parameters: {', '.join(field_names)}"])`
6. Reject extra arguments with the same `TYPE` error text as `evaluate_instantiation`.
7. Run the constructor code object with `this` set to the new object.
8. Apply locks when the call site declares them.
9. Push the new object.

`src/vm/declarations.py construct_object(image, type_id, call_site, arguments, frame)` is the single implementation. It does not call `evaluate_instantiation` because that helper evaluates AST nodes. It must produce the same object shape, error text and field order.

### Field access

- `LOAD_FIELD field_const` resolves the field descriptor from the constant pool, checks privacy when the access is dynamic, and reads `object.data[field_name]`.
- `STORE_FIELD field_const` calls `copy_value(value)` then writes. It checks the field const lock and raises `powang_error_constant_assign` on violation.
- `LOAD_MEMBER name_const` uses a runtime name string. It first looks for a property, then a method. A private property from outside the owning type raises the same `private property` error as the tree walker.
- `STORE_MEMBER name_const` writes a property by name. It rejects an unknown member with the same identifier error as the tree walker.
- `LOAD_MEMBER_SAFE name_const` returns `nova` when the receiver is `nova`, otherwise it behaves like `LOAD_MEMBER`.
- `_private_access_allowed(owner)` is exposed as `src.runtime.private_access_allowed(owner)` in this phase. The VM uses the wrapper so the private access state is shared with the tree walker.

### Methods

- `CALL_METHOD call_site` reads the receiver from the stack, resolves the concrete type name, then looks up the method in `state.scope.ObjectTypes[-1][type_name]`.
- `find_method` returns the `PowangFunction` with `code` set. Dispatch then calls `VM.call_function` through `src.runtime.callMethod`, which already delegates when the function carries `code`.
- An unknown method raises the same `IDENTIFIER` or `METHOD` error as the tree walker.
- A private method from outside the owning type raises the same `private method` error.
- `CALL_STATIC` resolves the type by `call_site.type_name` and the method by name. A private static method from outside raises `private static method`.
- `CALL_OPERATOR` is used for explicit trait qualified operator calls. It calls the public `src.runtime.callOperatorMethod` wrapper around `_call_operator_method`.
- `this` is `frame.receiver`. `LOAD_THIS` pushes it. A method code object has `CodeObject.is_method` true and `parameter_count` excludes `this`.

### Operator dispatch

- Arithmetic and comparison handlers already call `performOperation`. That function dispatches `Add`, `Subtract`, `Multiply`, `Divide`, `Remainder`, `Negate` and `Compare` on `PowangObjectType` values. V4 does not add a second dispatch table.
- The `Compare` trait returns an `int`. `performOperation` converts that integer to a boolean with the same rules as the tree walker.
- The right operand fallback rule, the trait qualified rule and the unsupported operation error are all inside `performOperation` and `_call_comparison_operator`. Do not duplicate them.
- `CALL_OPERATOR` exists for source level trait qualified calls such as `Add.add(left, right)`. Its descriptor names the trait and the method.

### Enums

- An enum value is a `PowangObjectType` with `data={"name": PowangString(variant)}`, `type_name` set to the enum name, `is_enum=True` and `defined=True`.
- `NEW_ENUM enum_id, variant` creates a new enum value with this shape.
- `LOAD_ENUM_MEMBER enum_id, variant` returns the variant instance from the enum map. It is the same object on every load so identity comparison and equality behave like the tree walker.
- Enum equality compares type name and variant name. Use the existing `PowangObjectType.__eq__` behavior.
- Enum display is `<Color: RED>` through the existing `explicitCastString` path.

### Locks

`SET_LOCKS flags` applies:

| Bit | Effect |
|---|---|
| 0 | `weak` property flag |
| 1 | `const` property flag |
| 2 | `structure_locked = True` |
| 3 | `elements_locked = True` |
| 4 | `defined = True` |

`STRUCTURE_LOCK` rejects length changes and method calls that add or remove elements. `ELEMENTS_LOCK` rejects element assignment. Both raise `powang_error_constant_assign` with the same detail text as the tree walker.

### Copy semantics

- `copy_value` on an object calls `PowangCopyConstructObjectType(value)`. This is the existing copy constructor behavior.
- A copied object has a new field dictionary. Field values are copied with `copy_value`, so array fields share storage until mutation and then clone through `ensure_unique`.
- Tasks, files, modules, handles, project values and references keep identity semantics.
- `STORE_FIELD` copies the value before writing. `LOAD_FIELD` returns the stored value and marks mutable children shared through `copy_value`.

### Match

V4 adds these pattern kinds:

- `object`: type name match and named or positional field patterns. A positional pattern maps entries to fields in declaration order.
- `enum`: type name and variant name match.
- `expression`: not a pattern kind. Expression position match uses the result slot lowering described in the lowering table.

Object pattern matching uses `object.getProperty(field, private_access_allowed(object))`. A missing property returns `None` and fails the match. A failed nested pattern fails the outer pattern. Bindings are written only after the full pattern succeeds, so a partial match does not leak bindings.

Expression match requires a checker proven catch-all case. The VM leaves `nova` in the result slot when no case matches, which matches a non-exhaustive statement match that does nothing. The checker rejects a non-exhaustive expression match before execution.

### Safe access and coalesce

- `LOAD_MEMBER_SAFE` only treats `nova` as absent. It does not catch errors from a present receiver.
- `??` only tests `nova`. It does not treat an undefined typed local as absent. This matches the tree walker.
- `?.` and `??` preserve left to right evaluation.

## Acceptance criteria

1. Every V4 opcode has an interpreter handler, a verifier rule and at least one unit test.
2. A type with two fields constructs with positional and named arguments and reads both fields.
3. A private field default is applied when the argument is missing.
4. A missing required field raises the exact `TYPE ERROR` text from `evaluate_instantiation`.
5. A private field read from outside the owning type raises the exact `private property` error.
6. A private static method call from outside raises the exact `private static method` error.
7. A constructor body can read and write `this` fields.
8. A copied object can be mutated without changing the original, including an array field.
9. An enum value prints as `<Color: RED>` and compares equal to the same variant and unequal to another variant.
10. `left + right` on a type with an `add` method returns the same value as the tree walker.
11. `left < right` on a type with a `compare` method returns the same boolean as the tree walker.
12. An unsupported operator on a user object raises the same `unsupported operation` error as the tree walker.
13. `SET_LOCKS` rejects a structure change and an element write with the same error text as the tree walker.
14. Object patterns, enum patterns and guards match the tree walker.
15. Expression position match returns the same value as the tree walker.
16. `object?.field` returns nova when the object is nova and the field value otherwise.
17. `left ?? right` evaluates `right` only when `left` is nova.
18. The V4 corpus reports zero mismatches.
19. `test_type_construction.py`, `test_enums.py` and `test_match_patterns.py` pass with `POWANG_ENGINE=vm`.
20. The existing suite is green and no existing test file changed.

## Verification commands

```powershell
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_types -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_fields -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_methods -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_enums -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_operator_dispatch -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_locks -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_match_objects -v
.\.venv\Scripts\python.exe -m unittest discover -s src\vm\tests -t . -p "test_*.py" -v
.\.venv\Scripts\python.exe -m src.vm.differential --corpus src\vm\tests\corpus\v4 --fail-fast
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
$env:POWANG_ENGINE = "vm"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_type_construction.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_enums.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_match_patterns.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_vm_types.py" -v
Remove-Item Env:\POWANG_ENGINE
.\.venv\Scripts\python.exe powang.py vm disasm src\vm\tests\corpus\v4\types.po
.\.venv\Scripts\python.exe powang.py vm diff src\vm\tests\corpus\v4\types.po
git diff --name-only -- tests
```

Update the golden snapshots only after a reviewed lowering change:

```powershell
$env:POWANG_UPDATE_GOLDEN = "1"
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_golden_disasm -v
Remove-Item Env:\POWANG_UPDATE_GOLDEN
```

## Differential test corpus

Create these files under `src/vm/tests/corpus/v4/`.

`types.po`:

```po
type Point[+] {
    | x: int;
    | y: int;

    fun constructor {
        if x < 0 {
            this.x = 0;
        }
    }

    fun this.sum(): int >> this.x + this.y;
    fun origin(): Point >> Point.[0, 0];
}

first := Point.[1, 2];
second := Point.[x >> 3, y >> 4];
println(first.x);
println(first.y);
println(first.sum());
println(second.sum());
println(Point.origin().sum());
```

`field_defaults.po`:

```po
type Box[+] {
    - value: int = 7;
    - secret: int = 9;

    fun this.reveal(): int >> this.value + this.secret;
}

box := Box.[];
println(box.reveal());
```

`methods.po`:

```po
type Counter[+] {
    | value: int;

    fun this.bump(step: int): int {
        this.value += step;
        return this.value;
    }

    fun make(value: int): Counter >> Counter.[value];
}

counter := Counter.[1];
println(counter.bump(2));
println(counter.bump(3));
println(Counter.make(10).value);
```

`copy_semantics.po`:

```po
type Bag[+] {
    | items: arr[int];
    | label: str;
}

first := Bag.[[1, 2], "a"];
second := first;
second.items[0] = 9;
second.label = "b";
println(first.items);
println(first.label);
println(second.items);
println(second.label);
```

`enums.po`:

```po
type Color enum {
    RED,
    GREEN,
    BLUE,
}

c := Color.RED;
println(c);
println(typeof(c));
println(c == Color.RED);
println(c == Color.GREEN);
println(c :: Color);
```

`operator_overloading.po`:

```po
type Vector[+] {
    | x: int;
    | y: int;

    fun this.add(other: Vector): Vector >> Vector.[this.x + other.x, this.y + other.y];
    fun this.subtract(other: Vector): Vector >> Vector.[this.x - other.x, this.y - other.y];
    fun this.multiply(scale: int): Vector >> Vector.[this.x * scale, this.y * scale];
    fun this.negate(): Vector >> Vector.[-this.x, -this.y];
    fun this.compare(other: Vector): int {
        if this.x < other.x { return -1; }
        if this.x > other.x { return 1; }
        return this.y - other.y;
    }
}

left := Vector.[1, 2];
right := Vector.[3, 4];
println((left + right).x);
println((right - left).x);
println((left * 3).y);
println((-left).y);
println(left < right);
println(left == right);
```

`locks.po`:

```po
type Locked[+] {
    | values: arr[int!];
    | label: str!;
}

item := Locked.[[1, 2], "fixed"];
println(item.label);
item.values[0] = 9;
```

`match_objects.po`:

```po
type Point[+] {
    | x: int;
    | y: int;
}

p := Point.[3, 4];
match p {
    case Point.[x, y] >> println(x + y);
}

match p {
    case Point.[x: px, y: py] >> println(px * py);
}

type Color enum {
    RED,
    GREEN,
}

c := Color.GREEN;
match c {
    case Color.RED >> println(0);
    case Color.GREEN >> println(1);
}
```

`match_expression.po`:

```po
type Point[+] {
    | x: int;
    | y: int;
}

fun describe(p: Point): int {
    return p match {
        case Point.[x: 0, y: 0] >> 0
        case Point.[x: 0, y: _] >> 1
        case _ >> 2
    };
}

println(describe(Point.[0, 0]));
println(describe(Point.[0, 5]));
println(describe(Point.[2, 3]));
```

`safe_access.po`:

```po
type Node[+] {
    | value: int;
}

present := Node.[5];
missing: @Node;
println(present?.value);
println(missing?.value);
println(missing ?? present);
```

`error_private.po`:

```po
type Box[+] {
    - secret: int = 9;
}

b := Box.[];
println(b.secret);
```

`error_missing_field.po`:

```po
type Pair[+] {
    | left: int;
    | right: int;
}

p := Pair.[1];
println(p);
```

## Golden disassembly cases

| Case | Source | Required assertions |
|---|---|---|
| `v4_types` | `src/vm/tests/corpus/v4/types.po` | `DECLARE_TYPE`, `CONSTRUCT`, `LOAD_FIELD`, `CALL_METHOD`, type and field constant indices |
| `v4_methods` | `src/vm/tests/corpus/v4/methods.po` | `CALL_METHOD` and `CALL_STATIC` descriptors, `LOAD_THIS`, `STORE_FIELD` |
| `v4_enums` | `src/vm/tests/corpus/v4/enums.po` | `LOAD_ENUM_MEMBER`, enum type index, variant index |
| `v4_operator_overloading` | `src/vm/tests/corpus/v4/operator_overloading.po` | `ADD`, `SUB`, `MUL`, `NEG`, `LT`, `EQ` have no inline operator method call |
| `v4_locks` | `src/vm/tests/corpus/v4/locks.po` | `SET_LOCKS` flags byte and placement after `CONSTRUCT` |
| `v4_match_objects` | `src/vm/tests/corpus/v4/match_objects.po` | Object pattern descriptor, enum pattern descriptor, field entries |
| `v4_match_expression` | `src/vm/tests/corpus/v4/match_expression.po` | Result slot store and load, failure targets, final `LOAD_LOCAL result` |
| `v4_safe_access` | `src/vm/tests/corpus/v4/safe_access.po` | `LOAD_MEMBER_SAFE`, `JUMP_IF_NOVA`, `JUMP_IF_NOT_NOVA`, coalesce order |

## Atomic commit plan

1. `vm(v4): add type table entries and field descriptors`
2. `vm(v4): lower type declarations and field defaults`
3. `vm(v4): add construction and field binding`
4. `vm(v4): add constructor body compilation`
5. `vm(v4): add field load and store`
6. `vm(v4): add private field and method access checks`
7. `vm(v4): add instance and static method dispatch`
8. `vm(v4): add object copy through the copy constructor`
9. `vm(v4): add enum declaration and variant loads`
10. `vm(v4): add object and enum match patterns`
11. `vm(v4): add expression position match`
12. `vm(v4): add operator trait dispatch`
13. `vm(v4): add comparison dispatch`
14. `vm(v4): add const and element locks`
15. `vm(v4): add safe member access and coalesce`
16. `vm(v4): add v4 corpus golden snapshots and type engine tests`

## Risks and rollback

| Risk | Mitigation | Rollback |
|---|---|---|
| Object layout differs from the tree walker | Construct with the same `PowangObjectType` shape and field order. Golden tests print the object | Revert the construction commit |
| Access control leaks private fields | Use the shared `private_access_allowed` wrapper and test same type, other type and dynamic access | Revert the access control commit |
| Operator dispatch duplicates tree rules | All arithmetic and comparison handlers call `performOperation` | Revert the operator commit. The language then loses operator overloading on the VM |
| Object copy is shallow | `copy_value` calls `PowangCopyConstructObjectType` and container fields share until `ensure_unique` | Revert the copy commit and force deep copies |
| Enum identity differs per load | `LOAD_ENUM_MEMBER` returns the cached variant instance from the enum map | Revert the enum commit |
| Expression match leaves the wrong value | Result slot is initialized to nova and overwritten by the matched case | Revert the expression match commit |
| Locks apply to the wrong target | `SET_LOCKS` runs after `CONSTRUCT` and before the value is stored | Revert the locks commit |
| Field default evaluation order changes | Defaults run in declaration order with earlier fields already bound | Revert the default commit and require explicit fields in V4 |
| `??` treats undefined as absent | `JUMP_IF_NOT_NOVA` only tests `nova`, tested with `@T` and uninitialized slots | Revert the coalesce commit |

## Exit gate

V4 is closed when all of these are true:

- [ ] Every V4 opcode has a handler, a verifier rule and a unit test.
- [ ] The V4 corpus reports zero mismatches.
- [ ] Type construction, named construction, defaults and constructor bodies match the tree walker.
- [ ] Field, method and static method privacy match the tree walker.
- [ ] Object copy semantics match the tree walker, including container fields.
- [ ] Enum display, identity and equality match the tree walker.
- [ ] Arithmetic, unary and comparison operator traits match the tree walker.
- [ ] Const and element locks match the tree walker.
- [ ] Object patterns, enum patterns, guards and expression match match the tree walker.
- [ ] `test_type_construction.py`, `test_enums.py` and `test_match_patterns.py` pass with `POWANG_ENGINE=vm`.
- [ ] The tree walker remains the default engine.
- [ ] The existing suite is green and no existing test file changed.
