# Phase 2C: traits and interfaces

## 1. Scope

This phase adds structural traits, trait annotations, trait-qualified methods and generic trait constraints.

In scope:

- `trait` declarations.
- Required properties and required methods.
- Default trait methods.
- Structural satisfaction with no `impl` blocks.
- Trait annotations on variables, parameters and return types.
- Generic constraints with `T: TraitA & TraitB`.
- Trait-qualified method definitions inside a type.
- Trait-qualified calls with `Trait.method(value, ...)`.
- Conflict and ambiguity diagnostics.
- LSP trait completion and highlighting.

Out of scope:

- Nominal traits.
- Trait inheritance.
- Generic traits with type parameters.
- Operator overloading through traits.
- Cross-module trait checking.
- Async and await.
- Formatter and linter.

## 2. Locked syntax

### 2.1 Trait declaration

```po
trait Drawable {
    | name: str;
    fun draw(): str;
    fun describe(): str {
        return $"name={this.name} draw={this.draw()}";
    }
}
```

Rules:

- A trait property is declared with `| name: type;` or `name: type;`.
- A required method is a function signature ending with `;`.
- A default method is a function with a body.
- Trait methods are instance methods. `this` is the concrete object at runtime.
- Trait methods may be overloaded.
- A trait member name must be unique across properties and methods.

### 2.2 Structural satisfaction

There is no `impl` block. A concrete type satisfies a trait when:

- It declares every trait property with an assignable type.
- It declares every required trait method with a compatible signature, or the trait provides a default method.
- A method is compatible when parameters are contravariant and the return type is covariant.
- A single unqualified method with a compatible signature satisfies every trait that requires that method.
- A trait-qualified method `fun Trait.method(...)` satisfies that trait only.

### 2.3 Trait annotations

```po
x: Drawable = Screen.["main", ...];
fun render(value: Drawable): str >> value.draw();
```

Assigning a concrete type to a trait checks structural satisfaction. A value with a trait type exposes only the trait contract.

### 2.4 Generic constraints

```po
fun render[T: Drawable](value: T): str >> value.draw();
fun render_all[T: Drawable & Named](value: T): str >> value.draw();
```

A concrete type argument must satisfy every constraint. Inside the body, method calls resolve against the constrained traits.

### 2.5 Trait-qualified methods

```po
type Screen[+] {
    | name: str;

    fun draw(): str >> "screen";

    fun Named.draw(): str >> $"screen:{this.name}";
}
```

`fun Trait.method` is an instance method of the type, qualified by the trait. It is used when:

- Two traits require the same method name with incompatible signatures.
- A trait needs a different implementation from the normal method.

Trait-qualified methods are public.

### 2.6 Trait-qualified calls

```po
Drawable.draw(value);
Named.draw(value);
```

The first argument is the receiver. The remaining arguments are the method arguments. This form selects one trait explicitly and removes ambiguity.

## 3. Checker model

Add `_TraitInfo`:

```text
name: str
properties: dict[str, str]
methods: dict[str, list[_Signature]]
required_methods: set[str]
default_methods: set[str]
```

Add to the checker:

- `self.traits: dict[str, _TraitInfo]`.
- `self.current_type_parameter_constraints: dict[str, list[str]]`.
- `self.in_trait_body: tuple[str, str] | None`.

### 3.1 Default body contract

A default method body is checked against a synthetic object type created from the trait declaration. The synthetic type exposes only:

- Declared trait properties.
- Declared trait methods, including defaults.
- No concrete members.

Accessing an undeclared member is an error:

```text
trait method describe uses member color which is not declared in the trait. Declare color in the trait or remove the usage.
```

The trait contract is never inferred from the default body. Only explicit declarations extend it.

### 3.2 Structural satisfaction

`_type_satisfies_trait(type_name, trait_name)` checks:

- Trait properties against the type properties.
- Required trait methods against:
  - The trait-qualified method for that trait.
  - The unqualified method.
  - The trait default method.
- Signature parameter contravariance and return covariance.

A trait type assigned to another trait is checked contract to contract.

### 3.3 Diagnostics

Incompatible concrete implementation:

```text
type Screen cannot satisfy Drawable: method draw has incompatible signatures
```

Generic constraint conflict:

```text
generic parameter T is constrained by Drawable and Named, which require incompatible signatures for draw. Use a single trait constraint or a trait-qualified call.
```

Ambiguous call:

```text
call to draw is ambiguous between Drawable.draw and Named.draw. Cast the value to one trait or use Trait.method.
```

Missing trait member:

```text
type Screen cannot satisfy Drawable: missing method draw
type Screen cannot satisfy Drawable: property name has type int, but the trait requires str
```

Trait-qualified definition mismatch:

```text
method Screen.Named.draw() does not match the signature required by Named.draw()
```

### 3.4 Generic constraints

Function and lambda signatures store `type_parameter_constraints`.

Call inference:

- Infer or take explicit concrete types for type parameters.
- Check each concrete type against every constraint.
- For multiple constraints, check shared method signatures.
- Inside a constrained body, method calls resolve against the constraints.
- If multiple constraints provide the method with incompatible signatures, report the conflict and require a trait-qualified call.

### 3.5 Method resolution

Method calls resolve in this order:

1. Native receiver methods.
2. Static methods on a type name.
3. Trait-qualified call when the owner name is a trait.
4. Trait method when the receiver type is a trait.
5. Constrained trait method when the receiver type is a type parameter.
6. Concrete unqualified method.
7. Trait-qualified method on the concrete type.
8. Trait default method for a satisfied trait.

A call is annotated with `resolved_trait` when a trait selection is needed at runtime.

## 4. Runtime model

Add a trait registry to `InterpreterState`:

```text
TraitRuntimeInfo
  name
  properties: set[str]
  required_methods: set[str]
  default_methods: dict[str, list[PowangFunction]]
```

Add to `PowangObjectType`:

```text
trait_methods: dict[str, dict[str, list[PowangFunction]]]
```

Runtime declaration:

- Register traits before use.
- Evaluate default method bodies into functions with `instance_method=True`.
- Store trait-qualified implementations on the object type under the trait name.

Runtime dispatch:

- `Trait.method(receiver, args...)` selects the trait explicitly.
- A call annotated with `resolved_trait` uses that trait.
- A direct call on an object prefers the unqualified method.
- If no unqualified method exists, a unique trait-qualified method is used.
- If several trait-qualified methods match with incompatible signatures, raise ambiguity.
- If no implementation exists, use a unique default method from a satisfied trait.
- `this` is always the concrete object.

## 5. LSP changes

- Highlight the `trait` keyword.
- Index trait declarations and their members.
- Complete trait methods after `Trait.`.
- Hover on a trait shows its declaration.
- Diagnostics from the checker are surfaced by the existing LSP path.

## 6. Tests

### 6.1 Parser

- Trait declaration with properties, required methods and defaults.
- Required method signature without a body.
- Generic constraints with one and two traits.
- Trait-qualified method definition.
- Trait-qualified method definition outside a type body is rejected.
- Duplicate trait member names are rejected.

### 6.2 Checker

- Concrete type satisfies a trait.
- Missing property and missing method errors.
- Incompatible property and method signature errors.
- Trait annotation assignment.
- Trait parameter and return types.
- Default body can use declared members.
- Default body cannot use undeclared members.
- Generic constraint success and failure.
- Multiple constraint conflict.
- Trait-qualified method definition compatibility.
- Ambiguous direct call.
- Trait-qualified call resolves ambiguity.

### 6.3 Runtime

- Method dispatch through a trait annotation.
- Default method dispatch.
- Trait-qualified method dispatch.
- Trait-qualified call.
- Conflicting traits requiring qualified methods.
- Constrained generic function dispatch.
- `this` inside a default method is the concrete object.

### 6.4 LSP

- Trait declaration indexing.
- Completion after `Trait.`.
- Syntax highlighting for `trait`.

## 7. Commit sequence

| Commit | Objective |
|---|---|
| T1 | Add trait parsing and trait-qualified method parsing. |
| T2 | Add the checker trait model, satisfaction and default body contract. |
| T3 | Add generic constraints and conflict diagnostics. |
| T4 | Add runtime trait registration and dispatch. |
| T5 | Add tests and examples. |
| T6 | Update docs, versions and LSP. |

## 8. Verification

From `C:\Users\zarap\Dev\Python\powang`:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -O -m unittest discover -s tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_traits.py" -v
```

From `C:\Users\zarap\Dev\Python\powang-lsp`:

```powershell
python -m unittest discover -s tests
node --test tests/protocol.test.js
python lsp_smoke.py
python scripts/check_versions.py
python scripts/check_vendored_src.py --reference ..\powang\src
npx vsce package --no-dependencies
python scripts/check_vsix.py powang-lsp-*.vsix
```

## 9. Acceptance criteria

- `trait` declarations parse and register.
- Concrete types satisfy traits structurally with no impl blocks.
- Trait annotations check assignments and method calls.
- Default methods use only the declared trait contract.
- Generic constraints enforce trait satisfaction.
- Conflicting traits require trait-qualified methods.
- Trait-qualified calls resolve ambiguity.
- Runtime dispatch works for concrete methods, qualified methods and defaults.
- The LSP highlights traits and completes `Trait.` members.
- All existing tests pass in normal and `-O` modes.
