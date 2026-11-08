# Phase 2B3: match destructuring and exhaustiveness

## 1. Scope

This phase adds destructuring patterns, range patterns and coverage warnings to `match`.

In scope:

- Array patterns.
- Tuple patterns.
- Object patterns.
- Rest bindings inside array and tuple patterns.
- Nested patterns.
- Numeric range patterns.
- Boolean and enum exhaustiveness warnings.
- Unreachable case warnings.
- LSP syntax highlighting and documentation updates.

Out of scope:

- Traits and interfaces.
- Cross-module type checking.
- Async and await.
- Formatter and linter.
- Package registry.
- Debugger.
- Range patterns in loops, which remain C-style loop sugar.

## 2. Locked syntax

### 2.1 Array patterns

```po
case [a, b, c] >> ...
case [head, ...tail] >> ...
case [first, ...] >> ...
case [0, rest] >> ...
```

An array pattern matches an `arr` or a `tup`. The pattern without a rest
binding requires an exact length. A rest binding captures the remaining
elements as a new container of the same kind as the subject.

### 2.2 Tuple patterns

```po
case .[a, b] >> ...
case .[a, ...tail] >> ...
```

A tuple pattern matches only a `tup`.

### 2.3 Object patterns

```po
case Point.[x, y] >> ...
case Point.[x: px, y: py] >> ...
case Point.[x: 0, y] >> ...
```

A bare field name binds the property to a variable with the same name. A
colon maps the property to a nested pattern. Object patterns match the
declared object type and then match each named property.

### 2.4 Range patterns

```po
case 0 >> 10 >> "low"
case -10 >> 0 >> "negative"
```

A range pattern has an inclusive lower bound and an exclusive upper bound.
The first `>>` separates the bounds. The second `>>` separates the pattern
from the case body. Range bounds must be numeric.

The parser uses lookahead. It treats two `>>` tokens as a range only when the
second operand parses as an expression and is followed by another `>>`.
Otherwise the first `>>` is the normal case separator.

### 2.5 Wildcards and bindings

Existing forms remain:

```po
case _ >> ...
case >> ...
case value >> ...
case value: int >> ...
```

A binding matches every value of the subject type and binds a copy of it.

### 2.6 Guards

Guards run after all bindings in the pattern have been bound.

```po
case [a, b] if a < b >> ...
```

## 3. Pattern model

Every pattern is a dictionary with a `kind` and source position.

```text
wildcard  { kind: "wildcard" }
literal   { kind: "literal", value: <expression> }
binding   { kind: "binding", value: <identifier>, type: <type or null> }
range     { kind: "range", start: <expression>, end: <expression> }
array     { kind: "array", entries: [pattern], rest: <rest or null> }
tuple     { kind: "tuple", entries: [pattern], rest: <rest or null> }
object    { kind: "object", type_name: str, entries: [{ field, pattern }] }
```

A rest entry is `{ "name": <identifier or null> }`.

## 4. Checker changes

### 4.1 Pattern checking

`_check_match_pattern(pattern, subject_type)` recursively checks:

- Literal patterns against the subject type.
- Binding types against the subject type.
- Range bounds must be numeric, and the subject must be numeric.
- Array patterns against `arr[T]` or `tup[...]`.
- Tuple patterns against `tup[...]`.
- Object patterns against `object:Type` and its declared properties.
- Nested patterns against the element or property type.

Unknown object types and unknown object fields are checker errors.

### 4.2 Coverage analysis

The checker records unguarded coverage:

- An unguarded wildcard or binding is a catch-all.
- Boolean literals cover `true` and `false`.
- Enum variants cover their variant.
- Literal patterns cover their value.
- Range patterns cover their static numeric interval when both bounds are
  numeric literals.

Guarded cases never contribute to exhaustiveness and never make later cases
unreachable.

### 4.3 Exhaustiveness warnings

New warning codes:

- `PW215`: non-exhaustive match.
- `PW216`: unreachable match case.

Boolean exhaustiveness:

```text
match on bool is not exhaustive; missing false
```

Enum exhaustiveness:

```text
match on Color is not exhaustive; missing BLUE
```

Only exact `bool` subjects and exact enum object subjects are checked. Other
types do not require a wildcard.

### 4.4 Unreachable cases

A case is unreachable when:

- An earlier unguarded catch-all already matches every value.
- An earlier unguarded literal covers the same value.
- An earlier unguarded range covers the entire range.
- An earlier unguarded range covers a numeric literal.

The warning is emitted on the unreachable pattern position.

## 5. Runtime changes

Add `_match_pattern(pattern, subject)` shared by `MATCH_STATEMENT` and
`MATCH_EXPRESSION`.

Rules:

- Literal patterns compare type and value equality.
- Binding patterns bind a copy of the subject.
- Range patterns compare `start <= subject < end`.
- Array patterns match `arr` and `tup`.
- Tuple patterns match `tup` only.
- Object patterns require the same `type_name` and then match properties.
- Nested bindings are added to the current case scope.
- A failed nested match discards the whole case scope.
- Guards run after all bindings.

## 6. LSP changes

- Highlight pattern brackets, rest bindings and range separators.
- Keep hover and completion unchanged.
- Document match patterns in the README.
- Sync the vendored powang source and bump the extension version.

## 7. Tests

### 7.1 Parser

- Array, tuple, object, range and nested patterns.
- Rest bindings.
- Negative range bounds.
- A normal case body starting with a literal is not misparsed as a range.
- Object field mapping.

### 7.2 Checker

- Array pattern element types.
- Tuple pattern arity.
- Object pattern field types.
- Unknown object field error.
- Range bound type error.
- Boolean exhaustiveness warning.
- Enum exhaustiveness warning.
- Wildcard suppresses exhaustiveness warnings.
- Unreachable case after a wildcard.
- Duplicate literal and duplicate enum variant warnings.
- Guarded duplicate does not warn.

### 7.3 Runtime

- Array and tuple destructuring.
- Rest bindings.
- Nested destructuring.
- Object destructuring with bare and mapped fields.
- Range matching, including exclusive upper bound.
- Guards with destructured bindings.
- No match returns `nova` in a match expression.

### 7.4 LSP

- Match pattern tokens highlight.
- Version and vendored source checks pass.

## 8. Commit sequence

| Commit | Objective |
|---|---|
| M1 | Add pattern parsing and positions. |
| M2 | Add runtime pattern matching. |
| M3 | Add checker pattern checks, coverage and warnings. |
| M4 | Add tests and examples. |
| M5 | Update docs, versions and LSP. |

## 9. Verification

From `C:\Users\zarap\Dev\Python\powang`:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -O -m unittest discover -s tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_match_patterns.py" -v
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

## 10. Acceptance criteria

- Array, tuple and object patterns destructure values.
- Rest bindings capture remaining elements.
- Nested patterns work.
- Range patterns use an inclusive lower bound and an exclusive upper bound.
- Boolean matches warn when a value is missing.
- Enum matches warn when a variant is missing.
- Unreachable cases warn.
- Guards are evaluated after bindings.
- All existing tests pass in normal and `-O` modes.
- The LSP vendored source is synced and version checks pass.
