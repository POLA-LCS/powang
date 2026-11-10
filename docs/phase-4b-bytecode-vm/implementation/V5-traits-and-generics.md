# V5: Traits and Generics

Purpose: deliver trait declarations, required and default methods, trait annotations, trait qualified methods and calls, generic constraints and trait conflict and ambiguity errors on the bytecode VM.

## Objective

At the end of V5 the VM executes structural traits. A trait declaration registers a runtime contract with required properties, required methods and default method code objects. A type satisfies a trait by declaring the required properties and methods, either as ordinary methods or as trait qualified methods. A trait annotation keeps the concrete object payload and exposes the trait contract.

Trait qualified calls search the type's trait method table first, then unqualified methods, then the trait default methods. Ambiguous unqualified calls raise the same error text as the tree walker and tell the user to cast to one trait or use `Trait.method`.

Generic constraints are checked at the callee boundary. When a type parameter is constrained by a trait, the callee prologue checks every argument bound to that type parameter with `CHECK_TRAIT`. A value crossing a dynamic boundary through a trait annotation uses `TRAIT_CAST`.

Semantic reference: `docs/phase-4b-bytecode-vm/04-compiler-lowering.md` sections 12.10 and 12.11, `docs/phase-4b-bytecode-vm/02-values-heap-and-frames.md` section 8.5, and `docs/phase-4b-bytecode-vm/05-runtime-semantics-and-debugging.md` section 13.3.

## Prerequisites

- V4 is `gate green`. User types, enums, methods, access control and operator dispatch work.
- The V4 corpus reports zero mismatches:

```powershell
.\.venv\Scripts\python.exe -m src.vm.differential --corpus src\vm\tests\corpus\v4 --fail-fast
```

- The baseline suite is green.

Contract surfaces this phase depends on:

- `src/vm/image.py`: `TraitInfo`, `TypeInfo.methods` trait name slot, `CallSite` dispatch value `trait`.
- `src/vm/declarations.py`: `declare_trait`, `find_trait_method`, `check_trait`, `trait_cast`.
- `src/vm/dispatch.py`: `call_trait`, `call_method`, ambiguity handling.
- `src/state.py`: `TraitRuntimeInfo`, `state.traits`.
- `src/runtime.py`: `callTraitMethod`, `callMethod`, `getFunctionCandidate`, `_object_satisfies_trait`, `_find_default_trait_method`, `_private_access_allowed`.

## Deliverables

### By file

| File | Work in V5 |
|---|---|
| `src/vm/compiler.py` | Trait declarations, default method code objects, trait qualified method definitions, trait annotations, `CHECK_TRAIT` prologue for constrained type parameters, trait qualified call sites |
| `src/vm/declarations.py` | `declare_trait`, `find_trait_method`, `find_default_method`, `check_trait`, `trait_cast`, `generic_constraints_for`, `emit_constraint_checks` |
| `src/vm/dispatch.py` | `call_trait`, trait method resolution, unqualified ambiguity detection, default method fallback |
| `src/vm/image.py` | `TraitInfo` population, `TypeInfo.methods` trait name, `CallSite.trait_name`, `CallSite.dispatch` value `trait` |
| `src/vm/interpreter.py` | Handlers for `DECLARE_TRAIT`, `CHECK_TRAIT`, `TRAIT_CAST`, `CALL_TRAIT` |
| `src/vm/tests/test_traits.py` | Trait declaration, required and default methods, annotation, qualified calls |
| `src/vm/tests/test_generics.py` | Generic constraints, type argument filtering, constraint failures |
| `src/vm/tests/test_trait_conflicts.py` | Ambiguous unqualified calls and qualified resolution |
| `src/vm/tests/golden/` | V5 golden disassembly snapshots |
| `src/vm/tests/corpus/v5/` | V5 differential corpus |
| `tests/test_vm_traits.py` | End to end VM engine test for traits and generics |

### By language feature

| Feature | Required behavior |
|---|---|
| Trait declaration | `trait Drawable` with a property and a method registers a contract |
| Required property | A type must declare the property to satisfy the trait |
| Required method | A type must declare the method or a trait qualified method |
| Default method | `fun describe(): str >> ...` becomes a code object in the trait table |
| Trait annotation | `value: Drawable = screen` keeps the concrete payload and exposes the contract |
| Trait qualified method definition | `fun Drawable.draw(): str` registers in the type trait method table |
| Trait qualified call | `value.draw()` on a trait annotation, and `Drawable.draw(value)` |
| Default method call | An unqualified call falls back to the trait default method |
| Generic constraint | `fun render[T: Drawable](value: T)` checks the argument at the callee boundary |
| Constraint failure | Raises the same trait satisfaction error text as the tree walker |
| Ambiguous unqualified call | Two trait methods with the same name raise the exact ambiguity error |
| Qualified resolution | `Drawable.draw(dual)` and `Named.draw(dual)` select the requested trait |

## Task checklist

- [ ] Add `TraitInfo` population and `DECLARE_TRAIT`.
- [ ] Lower trait declarations and required properties and methods.
- [ ] Compile default method bodies as trait code objects.
- [ ] Add trait qualified method definitions to the type method table.
- [ ] Add `CHECK_TRAIT` and `TRAIT_CAST` handlers.
- [ ] Lower trait annotations with `CAST_ASSIGN` or `TRAIT_CAST`.
- [ ] Add `CALL_TRAIT` and trait method resolution.
- [ ] Add default method fallback.
- [ ] Add generic constraint metadata and callee prologue checks.
- [ ] Add ambiguity detection and the exact conflict error text.
- [ ] Add V5 unit tests, corpus, golden snapshots and the trait engine test.

## Lowering table

| Source construct | Emitted instruction sequence |
|---|---|
| `trait Drawable` with a property and a method | module init `DECLARE_TRAIT trait_id`, `STORE_GLOBAL name` |
| `trait Drawable { fun describe(): str >> ...; }` | default method code object stored in `TraitInfo.methods`, `DECLARE_TRAIT` registers it |
| `fun Drawable.draw(): str { ... }` | method code object with `trait_name` metadata in `TypeInfo.methods` |
| `fun this.draw(): str { ... }` | ordinary method code object in `TypeInfo.methods` |
| `value: Drawable = screen` with a concrete `screen` | evaluate `screen`, `CAST_ASSIGN Drawable_spec`, `STORE_LOCAL value` |
| `value: Drawable = dynamic_value` | evaluate `dynamic_value`, `TRAIT_CAST trait_id`, `CAST_ASSIGN Drawable_spec`, `STORE_LOCAL value` |
| `value.draw()` where `value` is statically a trait | evaluate `value` as receiver, evaluate args, `CALL_TRAIT call_site` with `trait_name` |
| `Drawable.draw(value)` | evaluate `value`, evaluate args, `CALL_TRAIT call_site` with `trait_name` |
| `this.draw()` inside a default method | `LOAD_THIS`, evaluate args, `CALL_TRAIT call_site` |
| `fun render[T: Drawable](value: T): str` | callee prologue `LOAD_LOCAL value_slot`, `CHECK_TRAIT Drawable`, `POP` |
| `fun render[T: Drawable](values: T...): str` | prologue iterates the variadic array and `CHECK_TRAIT` per element |
| `dynamic as Drawable` | evaluate `dynamic`, `TRAIT_CAST trait_id`, `CAST Drawable_spec` |
| `Drawable` in an `any` union annotation | `BOX_ANY` carries the trait spec. A dynamic use emits `TRAIT_CAST` before the member call |

`CHECK_TRAIT` leaves the value on the stack. The prologue pops it. `TRAIT_CAST` also leaves the value on the stack.

## Runtime semantics notes

### Trait table

A `TraitInfo` entry carries:

- `name`: the trait name.
- `properties`: required property names in declaration order.
- `methods`: one tuple per method: `(name, code_index, has_default)`. `code_index` is `-1` when the method has no default.

`DECLARE_TRAIT trait_id` does the following:

1. Create a `TraitRuntimeInfo` with the trait name.
2. Fill `properties` from `TraitInfo.properties`.
3. Fill `declared_methods` and `required_methods` from the methods without defaults.
4. Fill `default_methods` with the code objects for methods with defaults.
5. Register the trait in `state.traits` under its name.
6. Push the trait object so the following `STORE_GLOBAL` binds the name.

`TraitRuntimeInfo.default_methods` values are lists of `PowangFunction` values to match the existing `callTraitMethod` contract. A single default method is a one element list.

### Trait satisfaction

`src.vm.declarations.check_trait(trait_name, value, where, position)` calls the public `src.runtime.object_satisfies_trait(owner, trait)` wrapper around `_object_satisfies_trait`. A value satisfies a trait when:

- It is a `PowangObjectType`.
- It declares every required property.
- It declares every required method, either as an ordinary method or as a trait qualified method for that trait.

When the value does not satisfy the trait, raise the same `TYPE` error text as the checker:

```text
type <Type> cannot satisfy <Trait>:
      | missing method <name>
```

For a missing property the detail is `missing property <name>`. The exact wording must match the tree walker.

`CHECK_TRAIT trait_id` pops nothing and pushes nothing beyond leaving the value in place. It is a guard for values that reach a generic or dynamic boundary.

`TRAIT_CAST trait_id` checks the value and leaves it unchanged on success. On failure it raises the same error as `CHECK_TRAIT`. It does not wrap the value. The static type after the cast is the trait annotation, and the runtime payload stays concrete.

### Trait qualified methods

- A method declared as `fun Drawable.draw(): str` is stored in the type's trait method table. The `TypeInfo.methods` entry has `trait_name` set to `Drawable`.
- `declare_type` populates `PowangObjectType.trait_methods` in the existing shape that `getTraitMethods(trait_name, method_name)` expects.
- An unqualified method is stored in `public_meths` or `private_meths`.

### Trait calls

`CALL_TRAIT call_site` reads the receiver and arguments and calls `src.runtime.callTraitMethod(where, trait_name, method_name, receiver, arguments, position)`.

`callTraitMethod` already performs the resolution order:

1. Trait qualified method on the receiver type.
2. Unqualified method on the receiver type.
3. Trait default method.
4. `IMPLEMENTATION` error when no implementation exists.

The VM must not duplicate this order. The receiver is the first stack value and the arguments follow in source order.

`CALL_METHOD` on a value with more than one trait implementation and no unqualified method must raise the same `TYPE` error text as the tree walker:

```text
call to <name> is ambiguous between <TraitA>.<name> and <TraitB>.<name>. Cast the value to one trait or use Trait.method.:
      | <TraitA>.<name>: <signature A>
      | <TraitB>.<name>: <signature B>
```

The ambiguity check belongs in `src.vm.dispatch.call_method` before it falls back to an unqualified candidate. It uses the same candidate list and the same signature rendering as the tree walker.

### Default methods

- A default method is an ordinary code object with a receiver, a `trait_name` and no static flag.
- `TraitInfo.methods` stores its code index and `has_default=True`.
- `DECLARE_TRAIT` creates the `PowangFunction` values and stores them in `default_methods`.
- `this` inside a default method is the receiver. `LOAD_THIS` pushes it.
- A default method that calls `this.draw()` lowers to `LOAD_THIS`, args, `CALL_TRAIT` with the same trait name. That is how `QualifiedOnly.[].describe()` reaches a trait qualified implementation.

### Generic constraints

- The parser already records `type_parameter_constraints` on function and method AST nodes.
- `FunctionInfo.flags["type_parameter_constraints"]` stores the mapping from type parameter name to the list of trait names.
- The compiler emits `CHECK_TRAIT` in the callee prologue for each parameter whose declared type is a constrained type parameter. The check order follows parameter order.
- For a variadic parameter of type `T...` with a constraint on `T`, the prologue checks each element of the variadic array.
- A constraint failure raises the same error as `CHECK_TRAIT`.
- The call site type arguments and the constraint metadata are both present. The V2 type argument filter still runs first. The prologue check is the runtime guarantee for dynamic values.
- Constraints on a type declaration `type Box[T: Drawable]` are checked at construction in the same prologue style.

### Trait annotations and `any`

- A trait annotation on a concrete value uses `CAST_ASSIGN` with a trait spec. `getUndefinedVariable` sees the trait name in `state.traits` and returns an `is_obj` target that keeps the concrete payload.
- A trait annotation on a dynamic value uses `TRAIT_CAST` first. The compiler knows the static type from the checker result. When the static type is `any`, a union or a type parameter without a concrete binding, it emits the cast.
- `BOX_ANY` may carry a trait spec in `declared_spec`. A later member access on the boxed value emits `TRAIT_CAST` before the trait qualified call.

### Access control

Trait method definitions and default methods follow the same private access rules as ordinary methods. A private method is not considered when checking trait satisfaction from outside the owning type. The checker enforces this for static calls. The runtime `object_satisfies_trait` uses the public method tables.

## Acceptance criteria

1. Every V5 opcode has an interpreter handler, a verifier rule and at least one unit test.
2. A trait with a required property and a required method is registered in `state.traits` with the correct sets.
3. A type that declares the property and method satisfies the trait.
4. A type that misses a required method raises the exact `cannot satisfy` error text.
5. `value: Drawable = screen` keeps the concrete type name and allows `value.draw()`.
6. `Drawable.draw(dual)` and `Named.draw(dual)` select the requested trait implementation.
7. An unqualified call on a type with two trait implementations and no unqualified method raises the exact ambiguity error.
8. A default method runs with the correct receiver and can call `this.draw()`.
9. `fun render[T: Drawable](value: T)` accepts a satisfying value and rejects a non satisfying one with the exact error text.
10. A variadic constrained parameter checks every element.
11. The V5 corpus reports zero mismatches.
12. `test_traits.py` passes with `POWANG_ENGINE=vm`.
13. The existing suite is green and no existing test file changed.

## Verification commands

```powershell
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_traits -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_generics -v
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_trait_conflicts -v
.\.venv\Scripts\python.exe -m unittest discover -s src\vm\tests -t . -p "test_*.py" -v
.\.venv\Scripts\python.exe -m src.vm.differential --corpus src\vm\tests\corpus\v5 --fail-fast
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
$env:POWANG_ENGINE = "vm"
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_traits.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_vm_traits.py" -v
Remove-Item Env:\POWANG_ENGINE
.\.venv\Scripts\python.exe powang.py vm disasm src\vm\tests\corpus\v5\traits.po
.\.venv\Scripts\python.exe powang.py vm diff src\vm\tests\corpus\v5\traits.po
git diff --name-only -- tests
```

Update the golden snapshots only after a reviewed lowering change:

```powershell
$env:POWANG_UPDATE_GOLDEN = "1"
.\.venv\Scripts\python.exe -m unittest src.vm.tests.test_golden_disasm -v
Remove-Item Env:\POWANG_UPDATE_GOLDEN
```

## Differential test corpus

Create these files under `src/vm/tests/corpus/v5/`.

`traits.po`:

```po
trait Drawable {
    | name: str;
    fun draw(): str;
    fun describe(): str >> $"name={this.name} draw={this.draw()}";
}

type Screen[+] {
    | name: str;
    fun this.draw(): str >> "screen";
}

screen := Screen.["main"];
value: Drawable = screen;
println(value.draw());
println(value.describe());
```

`trait_qualified.po`:

```po
trait Drawable {
    fun draw(): str;
}

trait Named {
    fun draw(): int;
}

type Dual[+] {
    fun Drawable.draw(): str >> "dual";
    fun Named.draw(): int >> 42;
}

dual := Dual.[];
drawable: Drawable = dual;
named: Named = dual;
println(drawable.draw());
println(named.draw());
println(Drawable.draw(dual));
println(Named.draw(dual));
```

`default_methods.po`:

```po
trait Described {
    fun draw(): str;
    fun describe(): str >> this.draw();
}

type QualifiedOnly[+] {
    fun Described.draw(): str >> "qualified";
}

println(QualifiedOnly.[].describe());
```

`generic_constraints.po`:

```po
trait Drawable {
    | name: str;
    fun draw(): str;
}

type Screen[+] {
    | name: str;
    fun this.draw(): str >> "screen";
}

fun render[T: Drawable](value: T): str >> value.draw();

println(render(Screen.["main"]));
```

`constrained_variadic.po`:

```po
trait Drawable {
    fun draw(): str;
}

type Screen[+] {
    fun this.draw(): str >> "screen";
}

fun render_all[T: Drawable](values: T...): int {
    count := 0;
    for value >> values {
        value.draw();
        count += 1;
    }
    return count;
}

println(render_all(Screen.[], Screen.[], Screen.[]));
```

`error_ambiguous.po`:

```po
trait A {
    fun draw(): int;
}

trait B {
    fun draw(): str;
}

type Dual[+] {
    fun A.draw(): int >> 1;
    fun B.draw(): str >> "b";
}

dual := Dual.[];
println(dual.draw());
```

`error_constraint.po`:

```po
trait Drawable {
    fun draw(): str;
}

type Plain[+] {
    | value: int;
}

fun render[T: Drawable](value: T): str >> value.draw();

println(render(Plain.[1]));
```

`error_missing_trait_method.po`:

```po
trait Drawable {
    fun draw(): str;
}

type Plain[+] {
    | value: int;
}

value: Drawable = Plain.[1];
```

## Golden disassembly cases

| Case | Source | Required assertions |
|---|---|---|
| `v5_traits` | `src/vm/tests/corpus/v5/traits.po` | `DECLARE_TRAIT`, default method code object, `CAST_ASSIGN` with a trait spec, `CALL_TRAIT` |
| `v5_trait_qualified` | `src/vm/tests/corpus/v5/trait_qualified.po` | `CALL_TRAIT` descriptors carry `Drawable` and `Named`, receiver first |
| `v5_default_methods` | `src/vm/tests/corpus/v5/default_methods.po` | `LOAD_THIS` inside the default code object, `CALL_TRAIT` for `this.draw()` |
| `v5_generic_constraints` | `src/vm/tests/corpus/v5/generic_constraints.po` | Type parameter metadata, prologue `LOAD_LOCAL`, `CHECK_TRAIT`, `POP` |
| `v5_constrained_variadic` | `src/vm/tests/corpus/v5/constrained_variadic.po` | Variadic flag, per element `CHECK_TRAIT` in the prologue |

## Atomic commit plan

1. `vm(v5): add trait table entries and declare trait`
2. `vm(v5): lower trait declarations`
3. `vm(v5): compile trait default method code objects`
4. `vm(v5): add trait qualified method tables`
5. `vm(v5): add check trait and trait cast`
6. `vm(v5): lower trait annotations`
7. `vm(v5): add trait qualified calls`
8. `vm(v5): add default method fallback`
9. `vm(v5): add generic constraint metadata and prologue checks`
10. `vm(v5): add trait conflict and ambiguity errors`
11. `vm(v5): add v5 corpus golden snapshots and trait engine tests`

## Risks and rollback

| Risk | Mitigation | Rollback |
|---|---|---|
| Trait resolution duplicates `callTraitMethod` | `CALL_TRAIT` calls `callTraitMethod` directly | Revert the call commit |
| Ambiguity error text differs | Compare full stderr for the conflict corpus | Revert the conflict commit |
| Default method receiver is wrong | Default code objects use `LOAD_THIS` and the same method frame shape | Revert the default method commit |
| Trait annotation loses the concrete payload | `CAST_ASSIGN` uses the `is_obj` branch and keeps `type_name` and data | Revert the annotation commit |
| Constraint failures happen at the wrong boundary | Constraints run in the callee prologue after binding and before the body | Revert the constraint commit |
| Generic type argument filtering conflicts with constraints | V2 filter runs first, then the prologue check | Revert the constraint commit and keep only static checks |
| Trait property check ignores private properties | `object_satisfies_trait` uses the public tables | Revert the check commit |

## Exit gate

V5 is closed when all of these are true:

- [ ] Every V5 opcode has a handler, a verifier rule and a unit test.
- [ ] The V5 corpus reports zero mismatches.
- [ ] Required and default trait methods match the tree walker.
- [ ] Trait annotations keep the concrete payload and expose the trait contract.
- [ ] Trait qualified and default method calls match the tree walker.
- [ ] Generic constraints match the tree walker for scalar, object and variadic arguments.
- [ ] Ambiguous unqualified calls produce the exact tree walker error text.
- [ ] `test_traits.py` passes with `POWANG_ENGINE=vm`.
- [ ] The tree walker remains the default engine.
- [ ] The existing suite is green and no existing test file changed.
