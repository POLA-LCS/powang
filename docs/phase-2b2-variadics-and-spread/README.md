# Phase 2B2: variadics and spread

## 1. Scope

This phase adds variadic user functions, prefix spread arguments, explicit type arguments and the `undef` inference for empty variadic calls.

In scope:

- Variadic function declarations.
- Generic type parameters on function declarations.
- Explicit type arguments on calls.
- Prefix spread in argument lists.
- Zero variadic arguments infer `undef`.
- Overload selection rules for concrete and template functions.
- Variadic signatures in function types and `typedeep`.
- LSP signature help, hover and `undef[type]` display.

Out of scope:

- Traits and interfaces.
- Match destructuring.
- Range patterns.
- Async and await.
- Formatter and linter.
- Package registry.
- Debugger.
- Cross-module type checking.
- First-class `reference` values.

## 2. Locked syntax

### 2.1 Declaration

Canonical form:

```po
fun sum[T](values: T...): T { ... }
```

Accepted sugar:

```po
fun sum[T, ...](values..): T { ... }
```

Both forms produce the same signature. The `...` inside the type parameter list marks the function as variadic. The `values..` or `values: T...` parameter binds the variadic values.

A function can mix fixed and variadic parameters:

```po
fun log_all[T](prefix: str, values: T...): nova { ... }
```

The variadic parameter must be last.

### 2.2 Calls

```po
sum(1, 2, 3);
sum[int](1, 2, 3);
sum(...values);
sum(...[1, 2, 3]);
```

Spread is a prefix operator and only valid in argument position. It cannot appear in a general expression.

Explicit type arguments are written `callee[type, ...](args...)`.

### 2.3 Zero arguments

If a variadic call receives zero variadic arguments, the type parameter is inferred as `undef`.

```po
sum();          ## T = undef, values = arr[undef]
```

`undef` is an internal type. It is not user-annotatable. It means "no element constrained this type parameter".

## 3. Type model

### 3.1 `undef`

Add an internal `undef` type to the checker and TypeSpec.

Rules:

- `undef` is assignable to every type parameter and every type.
- No user annotation may name `undef`.
- `undef` is only produced by empty variadic inference and by the LSP display convention for uninitialized variables.
- `arr[undef]` is the runtime representation of an empty variadic argument list.

The runtime does not need a new value class. The empty `PowangArray` is enough. `undef` is a checker-level type.

### 3.2 Function signatures

Extend `_Signature` with:

- `variadic: bool`.
- `variadic_index: int | None`.
- `type_parameters: list[str]`.
- `variadic_type: str | None`.

The canonical function type rendering for a variadic function is:

```text
fun[T..., ret]
```

The `...` marks the final parameter as variadic. A fixed function type remains `fun[arg1, arg2, ret]`.

TypeSpec function shapes get a `variadic` flag. Rendering and parsing must round-trip `fun[T..., ret]`.

### 3.3 Overload selection

Rules, in order:

1. If the call has explicit type arguments, keep only templates whose type parameter count matches.
2. Prefer an exact concrete overload whose parameter types match the arguments.
3. Then prefer a generic template whose inferred types match.
4. If two templates match equally, report ambiguity.
5. A variadic overload is preferred over a non-variadic overload only when the non-variadic overload does not match.
6. Explicit type arguments force the template path even when a concrete overload exists.

Example:

```po
fun add(a: int, b: int): int >> a + b;
fun add[T](a: T, b: T): T {
    println("TEMPLATE");
    return a + b;
}

add(1, 2);       ## concrete overload
add[int](1, 2);  ## explicit template, prints TEMPLATE
```

## 4. Parser changes

### 4.1 Function type parameters

Extend `helper_FunDeclaration` and `helper_LambdaExpression` to parse an optional type parameter list after the function name.

Accepted forms:

```po
fun id[T](args: T...): T
fun id[T, ...](args..): T
```

The type parameter list is stored on the function node as `type_parameters` and `variadic`.

### 4.2 Variadic parameter

Add support for:

```po
values: T...
values..
```

The parameter node stores `variadic: True` and its element type.

The variadic parameter must be the last parameter.

### 4.3 Explicit type arguments on calls

Extend the call parser so `name[type, ...](args...)` produces a call node with `type_arguments`.

The parser must distinguish this from indexing:

- `name[type](args)` is a call with type arguments.
- `name[index]` is an index expression.
- `name[type].method(args)` is a method call on a type reference.

Look ahead for `](` to decide.

### 4.4 Spread

Add an `ELLIPSIS` expression prefix in argument lists.

```po
sum(...values);
sum(...[1, 2, 3]);
```

Spread is only accepted where an argument is expected. Using it elsewhere is a syntax error.

## 5. Checker changes

### 5.1 Function signatures

`_make_signature` records:

- Type parameters.
- Variadic flag and index.
- Variadic element type.
- The rendered function type.

### 5.2 Call inference

`_infer_call` handles:

- Explicit type arguments.
- Binding type parameters from fixed arguments.
- Binding the variadic parameter from the remaining arguments.
- Zero remaining arguments set the type parameter to `undef`.
- Checking each variadic argument against the element type.
- Returning the inferred return type after substitution.

### 5.3 Inside the body

The variadic parameter is bound as `arr[T]` in the function body. Indexing, iteration and native array methods work as usual.

### 5.4 Function-typed values

`_signature_from_function_type` understands `fun[T..., R]`.

Calls through function-typed values check the fixed arguments and the variadic tail.

### 5.5 LSP `undef[type]` display

This is a display convention, not a language type.

The LSP marks a typed declaration with no initializer as uninitialized:

```po
x: int;                  ## LSP hover shows x: undef[int]
handler: fun[int, int];  ## LSP hover shows handler: undef[fun[int, int]]
x: int = 5;              ## LSP hover shows x: int
```

Rules:

- Only the LSP uses `undef[type]`.
- The checker still treats `x: int` as `int`.
- The runtime still creates an undefined `int` value.
- The display appears in hover and inlay hints.
- The `undef` display does not appear in completion detail or signature help.

## 6. Runtime changes

### 6.1 Function metadata

Extend `PowangFunction` with:

- `variadic: bool`.
- `variadic_index: int | None`.
- `type_parameters: list[str]`.

### 6.2 Argument binding

`checkFunctionArguments` and `resolveNamedArguments` collect extra positional arguments into a `PowangArray` for the variadic parameter.

Named arguments do not target the variadic parameter in this phase.

### 6.3 Spread

The call evaluator expands spread arguments before argument binding:

```po
sum(...values);
```

The spread source must be an `arr`, `tup` or `set`. A map spreads to an array of key-value tuples. A string spreads to an array of one-character strings.

### 6.4 Runtime metadata

`typedeep` renders variadic signatures as `fun[T..., R]`.

Explicit type arguments are erased at runtime.

## 7. LSP changes

- Signature help shows `values: T...`.
- Hover shows the variadic signature and the `undef[type]` display for uninitialized variables.
- Completion adds a variadic function snippet.
- Diagnostics explain wrong variadic argument types and non-last variadic parameters.
- Inlay hints show `undef[type]` for uninitialized typed declarations.

## 8. Tests

### 8.1 Parser

- Canonical variadic declaration.
- Sugar variadic declaration.
- Mixed fixed and variadic parameters.
- Variadic parameter not last is rejected.
- Explicit type arguments on calls.
- Spread in argument lists.
- Spread outside arguments is rejected.

### 8.2 Checker

- Concrete overload wins over template.
- Explicit type arguments force the template.
- Zero variadic arguments infer `undef`.
- Variadic element type mismatch.
- Fixed argument before variadic.
- Function type round trip for `fun[T..., R]`.
- Calling a variadic function-typed value.

### 8.3 Runtime

- Variadic call with zero, one and many arguments.
- Fixed and variadic arguments together.
- Spread from array, tuple and set.
- Spread from map and string.
- Variadic parameter behaves as an array.
- `typedeep` reports the variadic signature.
- Task calls with variadic functions.

### 8.4 LSP

- Signature help shows the variadic parameter.
- Hover shows `x: undef[int]` for `x: int;`.
- Hover shows `x: int` for `x: int = 5;`.
- Inlay hints show `undef[type]`.
- Variadic function completion snippet.

## 9. Commit sequence

| Commit | Objective |
|---|---|
| V1 | Add `undef` to TypeSpec and the checker. |
| V2 | Parse type parameters and variadic parameters. |
| V3 | Checker signature model and zero argument inference. |
| V4 | Runtime variadic argument binding. |
| V5 | Parse explicit type arguments and spread. |
| V6 | Checker variadic calls and overload rules. |
| V7 | Runtime spread and variadic metadata. |
| V8 | LSP signature help, hover and `undef[type]` display. |
| V9 | Examples, docs, version bump and release checks. |

## 10. Verification

From `C:\Users\zarap\Dev\Python\powang`:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -O -m unittest discover -s tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_variadics.py" -v
uv build --wheel
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

## 11. Risks

| Risk | Mitigation |
|---|---|
| `undef` becomes a real user type | Keep it internal and reject annotations that name it |
| Type parameter inference becomes ambiguous | Test concrete versus template overloads and explicit type arguments |
| Spread conflicts with array literals | Parse spread only in argument position |
| Variadic runtime binding breaks named arguments | Keep named arguments out of variadic parameters in this phase |
| Function type rendering changes break existing `fun[...]` types | Round-trip tests for fixed and variadic function types |
| LSP `undef[type]` leaks into the checker | Keep the display in the LSP index only |

## 12. Acceptance criteria

- Variadic declarations parse in both canonical and sugar forms.
- Zero variadic arguments infer `undef`.
- Explicit type arguments select the template overload.
- Spread expands arrays, tuples and sets.
- Variadic parameters behave as arrays inside the function body.
- Fixed and variadic arguments can be mixed.
- `typedeep` reports variadic signatures.
- The LSP shows `undef[type]` for uninitialized typed variables and normal types for initialized variables.
- All existing tests pass in normal and `-O` modes.
