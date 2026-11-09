# Phase 3C: operator overloading through traits

## 1. Scope

This phase adds operator overloading through built-in structural traits.

In scope:

- Arithmetic operators `+`, `-`, `*`, `/` and `%`.
- Unary minus.
- Comparison operators `==`, `!=`, `<`, `<=`, `>` and `>=`.
- Compound assignments through the existing binary operator path.
- Trait-qualified operator methods such as `fun Add.add`.
- Operator traits with custom trait-qualified methods.
- Operator use on trait-annotated values.
- Operator use inside generic constraints such as `T: Add`.
- Operator overload selection for different right operand types.
- Runtime dynamic dispatch with ambiguity detection.
- Checker diagnostics for operand mismatches, invalid compare return types, async operator methods and ambiguity.
- LSP completion, hover, semantic tokens and diagnostics for operator traits.

Out of scope:

- Logical operators `&&`, `||` and `!`.
- Null coalescing `??`.
- Pipeline `:>`.
- Type comparison `::` and `!:`.
- `as`.
- Indexing `[]` and index assignment.
- Reverse operators such as `1 + point`.
- Operator overloading on native types.
- Index or iterator overloading.

## 2. Built-in operator traits

The compiler provides these reserved traits:

| Trait | Method | Required signature | Operator |
|---|---|---|---|
| `Add` | `add` | `fun add(other: any): any` | `+` |
| `Subtract` | `subtract` | `fun subtract(other: any): any` | `-` |
| `Multiply` | `multiply` | `fun multiply(other: any): any` | `*` |
| `Divide` | `divide` | `fun divide(other: any): any` | `/` |
| `Remainder` | `remainder` | `fun remainder(other: any): any` | `%` |
| `Negate` | `negate` | `fun negate(): any` | unary `-` |
| `Compare` | `compare` | `fun compare(other: any): int` | `==`, `!=`, `<`, `<=`, `>`, `>=` |

The `any` parameter is a gradual contract. A concrete method with a narrower parameter type is allowed, because the checker uses the concrete signature to validate the actual right operand.

The trait names are reserved. A user trait named `Add`, `Subtract`, `Multiply`, `Divide`, `Remainder`, `Negate` or `Compare` is rejected by the checker and by the runtime.

## 3. Declaring an operator

An operator method is an instance method with the mapped method name.

```po
type Vector[+] {
    | x: int;
    | y: int;

    fun this.add(other: Vector): Vector >> Vector.[this.x + other.x, this.y + other.y];
    fun this.subtract(other: Vector): Vector >> Vector.[this.x - other.x, this.y - other.y];
    fun this.multiply(scale: int): Vector >> Vector.[this.x * scale, this.y * scale];
    fun this.negate(): Vector >> Vector.[-this.x, -this.y];
    fun this.compare(other: Vector): int {
        if this.x < other.x {
            return -1;
        }
        if this.x > other.x {
            return 1;
        }
        return this.y - other.y;
    }
}
```

The type now supports:

```po
left := Vector.[1, 2];
right := Vector.[3, 4];

sum := left + right;
difference := left - right;
scaled := left * 3;
negated := -left;

print(left < right);
print(left == right);

left += right;
```

Operator methods are instance methods. A static method named `add` does not overload `+`.

## 4. Trait-qualified implementations

A type may implement the built-in operator trait explicitly.

```po
type Point[+] {
    | x: int;

    fun Add.add(other: Point): Point >> Point.[this.x + other.x];
    fun Compare.compare(other: Point): int >> this.x - other.x;
}
```

The checker validates the method against the built-in trait contract. The runtime prefers the trait-qualified method over an unqualified method.

Custom traits may also qualify the implementation.

```po
trait Arithmetic {
    fun add(other: any): any;
    fun compare(other: any): int;
}

type Point[+] {
    | x: int;

    fun Arithmetic.add(other: Point): Point >> Point.[this.x + other.x];
    fun Arithmetic.compare(other: Point): int >> this.x - other.x;
}
```

A value annotated with `Arithmetic` uses those methods for operators. An untyped value with only `Arithmetic.add` also resolves dynamically when the trait method name is unambiguous.

## 5. Trait annotations and generic constraints

The built-in traits can be used in annotations.

```po
value: Add = Vector.[1, 2];
result := value + Vector.[3, 4];
```

They can also be used as generic constraints.

```po
fun add_all[T: Add](left: T, right: T): T {
    return left + right;
}
```

The checker resolves `left + right` against the `Add` contract. The runtime dispatches to the concrete operator method.

## 6. Comparison mapping

`compare` returns an integer.

```text
compare result < 0   a < b, a <= b, a != b
compare result == 0  a == b, a <= b, a >= b
compare result > 0   a > b, a >= b, a != b
```

The exact mapping is:

| Operator | Condition |
|---|---|
| `==` | `compare == 0` |
| `!=` | `compare != 0` |
| `<` | `compare < 0` |
| `<=` | `compare <= 0` |
| `>` | `compare > 0` |
| `>=` | `compare >= 0` |

The runtime requires `compare` to return `int`. Returning another type is an `[OPERATION ERROR]`.

A type without a `compare` method keeps the previous comparison behavior. Object equality remains structural, and ordering falls back to the native operation.

## 7. Overload selection

A type may declare multiple operator methods with the same name and different parameter types.

```po
type Point[+] {
    | x: int;

    fun this.add(other: Point): Point >> Point.[this.x + other.x];
    fun this.add(scale: int): Point >> Point.[this.x + scale];
}
```

The checker selects the operator method whose parameter accepts the right operand. Exact matches score higher than trait, `obj` and `any` parameters. If multiple equally specific methods remain and their signatures differ, the operator is ambiguous.

The runtime uses the same overload resolution through the normal method-call scoring.

## 8. Runtime dispatch

The runtime resolves an operator method in this order:

1. The trait recorded by the checker in `resolved_operator_trait`.
2. The unqualified instance method with the mapped name.
3. The only trait-qualified method with the mapped name.
4. If several trait-qualified methods exist and no static trait is available, report an ambiguity.

The checker records the selected trait on the binary or unary node. This keeps trait-annotated and generic values on the intended trait. Dynamic `any` values fall back to the unqualified or unambiguous trait method.

## 9. Diagnostics

Right operand mismatch:

```text
ln: 6 | [TYPE ERROR] (in operator +) Types doesn't match:
      | expected object:Point
      | but int was encounter
```

Invalid comparison return type:

```text
ln: 6 | [TYPE ERROR] (in operator <) operator method 'compare' does not satisfy Compare.compare:
      | required: fun[any, int]
      | found: fun[object:Bad, str]
```

Async operator method at the use site:

```text
ln: 6 | [TYPE ERROR] (in operator +) operator method 'add' cannot be async:
      | remove async from the operator method
```

Ambiguous overloads:

```text
[PACKAGE ERROR] (in operator +) operator is ambiguous between multiple overloads
```

Invalid arity:

```text
[PACKAGE ERROR] (in operator +) operator method 'add' must accept exactly one operand
```

Reserved trait name:

```text
[TYPE ERROR] (in trait declaration) trait 'Add' is reserved for operator overloading:
      | choose a different trait name
```

## 10. Limitations

- Only the left operand is considered for operator overloading. `1 + point` is not reversed.
- Logical, coalescing, pipeline and type-comparison operators are not overloadable.
- Indexing and index assignment are not overloadable in this phase.
- Static methods named after operators are ordinary static methods and do not overload operators.
- Operator methods cannot be async. The checker reports this when the operator is used, and the runtime rejects an async candidate.
- A dynamically typed value with several trait-qualified methods for the same operator is ambiguous. Annotate it with the intended trait.
- All operator methods follow normal member access rules, but operator syntax can call private operator methods because the checker does not model member access in operator expressions.

## 11. Tests

Powang tests cover:

- Arithmetic and unary operators.
- Comparison operators.
- Compound assignments.
- Trait-qualified operator implementations.
- Custom trait-qualified operator methods.
- Trait annotations and generic constraints.
- Overload selection by right operand type.
- Operand type errors.
- Invalid compare return types.
- Async operator methods.
- Static methods that do not overload operators.
- Reserved trait names.
- Ambiguous dynamic dispatch.
- The operator overloading example.

LSP tests cover:

- Operator trait semantic tokens.
- Operator trait completion and hover.
- Operator operand diagnostics.

## 12. Acceptance criteria

- `+`, `-`, `*`, `/`, `%` and unary `-` dispatch to structural operator methods.
- `==`, `!=`, `<`, `<=`, `>`, `>=` dispatch through `compare`.
- Compound assignments use the overloaded operators.
- Trait-qualified implementations work.
- Trait annotations and generic constraints work.
- Overloads select by right operand type.
- Operand mismatches and invalid compare signatures are rejected.
- Reserved operator trait names are rejected.
- The full powang test suite passes in normal mode and under `python -O`.
- The LSP test suite, smoke test, version check and vendored source check pass.
