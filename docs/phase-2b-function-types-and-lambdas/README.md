# Phase 2B: function types and lambdas

## 1. Scope

This phase adds first-class function types and lambda expressions.

In scope:

- Function type annotations with `fun[arg_types..., ret_type]`.
- Lambda expressions with block and expression bodies.
- Named lambdas for recursion.
- Default capture by value.
- Mutable capture with `fun &`.
- Function-typed variables, parameters and return values.
- Calling a function-typed value.
- Function type checking, inference and runtime metadata.
- LSP highlighting, hover and snippets for function types and lambdas.

Out of scope:

- Variadic user functions.
- Spread arguments.
- Traits and interfaces.
- Async and await.
- Formatter and linter.
- Package registry.
- Debugger.
- Cross-module type checking.
- First-class references.
- Overloaded function values without an explicit target signature.

## 2. Locked syntax

### 2.1 Function types

The function type is:

```po
fun[arg_types..., ret_type]
```

The last type is the return type. The preceding types are the parameters.

Examples:

```po
fun[int]                 ## zero arguments, returns int
fun[int, int]            ## one int argument, returns int
fun[int, str, bool]      ## int and str arguments, returns bool
fun[nova]                ## zero arguments, returns nova
fun[int, fun[int, int]]  ## one int argument, returns a function
fun[fun[int, int], int]  ## one function argument, returns int
```

Function types are positional. They do not carry parameter names or default values. Named arguments remain available only on direct calls to declarations.

A bare `function` annotation remains the dynamic function type and accepts any function value.

### 2.2 Lambdas

Lambda expressions use the existing `fun` keyword in expression position:

```po
double := fun(x: int): int >> x * 2;

double := fun(x: int): int {
    return x * 2;
};
```

A lambda can appear anywhere an expression is accepted:

```po
apply(fun(x: int): int >> x * 2, 5);

values :> transform(fun(x: int): int >> x + 1);
```

A named lambda can call itself:

```po
factorial := fun fact(n: int): int >>
    n <= 1 ?? 1 :> fact(n - 1) * n;
```

A variable can be declared with a function type and assigned a named function or a lambda:

```po
x: fun[int, int];
x = double;
```

The same works with inferred declarations and later assignment:

```po
x := double;
x = fun(value: int): int >> value * 3;
```

### 2.3 Capture semantics

Default capture is by value:

```po
base := 10;
add_base := fun(value: int): int >> value + base;
base = 20;
print(add_base(1));   ## 11
```

The `&` marker after `fun` captures by reference:

```po
counter := 0;
bump := fun &(value: int) {
    counter += value;
};
bump(2);
print(counter);       ## 2
```

A named mutable lambda is also allowed:

```po
bump := fun &add(value: int) {
    counter += value;
};
```

A lambda captures the current lexical scope. It can read global variables, local variables, functions and user types. If it appears inside a method, it captures the current `this` value.

## 3. Type system design

### 3.1 Canonical representation

Function types must not become a fifth type representation. Extend `src/typespec.py` with a function shape.

Add:

- `Kind.FUNCTION`.
- `Shape.FUNCTION` with `parameters: tuple[TypeSpec, ...]` and `return_type: TypeSpec`.

The rendered form is `fun[param1, param2, ret]`.

Examples:

```text
fun[int]
fun[int, int]
fun[int, str, bool]
```

The parser, checker, runtime casts and LSP all use `TypeSpec` for function types. The checker may still store the rendered string in its existing string-based type model, but it must parse and validate function types through `typespec.type_of_str`.

### 3.2 Assignability

Start with invariant function types:

- Same parameter count.
- Each target parameter type is exactly equal to the source parameter type.
- The return type is exactly equal to the source return type.

This keeps the first implementation predictable. Contravariant parameters and covariant returns can be added later after tests exist.

A function value without a declared signature is assignable to any function type only when the value is dynamically typed as `any`. A bare `function` target accepts any function value.

### 3.3 Function value inference

- A function declaration with one signature has the type `fun[param_types..., return_type]`.
- A function declaration with multiple overloads is still callable. Assigning it to a function-typed variable requires the target signature to select one overload. If the target does not disambiguate, report an ambiguity error.
- A lambda has the type built from its parameter annotations and its return annotation. If the return type is omitted, infer it from the body.
- A function-typed variable called as a function uses the parameter and return types from its function type.
- `typedeep` on a function returns its function type. `typeof` stays `function`.

## 4. Parser changes

### 4.1 Function type annotations

In `src/parser.py`, extend `_TypePrimary` to recognize `fun` followed by `[`.

Parse a comma-separated list of types until `]`. The list must contain at least one type. The last type is the return type. The preceding types are parameters.

Build a type node with:

- `value: 'fun'`.
- `parameters: list[type nodes]`.
- `return_type: type node`.
- The existing weak, const and reference qualifiers.

Function types can appear in any type position, including array elements, map keys and values, set elements, tuple elements and union branches.

### 4.2 Lambda expressions

Add `FUN_EXPRESSION` to `src/lexer/token.py`.

In `PrimaryExpression`, recognize `fun` in expression position. Parse:

1. Optional `&` for mutable capture.
2. Optional name for a named lambda.
3. Optional type parameters. Defer type parameters in this slice.
4. Parameter list using the existing function parameter grammar.
5. Optional return type.
6. Either a block or `>>` expression body.

Build a `FUN_EXPRESSION` node with:

- `name`.
- `mutable_capture`.
- `args`.
- `return`.
- `body` or `return_expr`.

The statement parser keeps handling `fun name(...)` as a declaration. Expression parsing only sees the lambda form, so there is no ambiguity.

## 5. Checker changes

### 5.1 Signatures

Extend `_Signature` in `src/typecheck.py` with a rendered `function_type` string. Build it from the parameter types and return type.

Add helpers:

- `_function_type_from_signature(signature) -> str`.
- `_signature_from_function_type(type_text) -> _Signature | None`.

### 5.2 Annotations

`_annotation_type` must handle function type nodes and return the rendered `fun[...]` form.

`_type_name_from_node` must handle function types for casts.

`_assignable` must compare function types through `typespec.assignable`.

### 5.3 Function declarations

`_make_signature` records the function type.

`_infer_identifier` for a function name returns the function type when the overload set has one signature. For multiple overloads, return `function` or `any` until the target signature selects one.

### 5.4 Lambda inference

For `FUN_EXPRESSION`:

1. Push a new scope.
2. Bind each parameter with its annotation, or `any` when unannotated.
3. Bind the lambda name to its own function type for recursion.
4. Check the body.
5. Determine the return type from the annotation or the inferred return expressions.
6. Pop the scope.
7. Return the rendered function type.

Lambda bodies must not leak local declarations outside the lambda.

### 5.5 Function-typed calls

`_infer_call` currently handles function names, builtins and external functions. Add:

- When the callee is a variable whose type is a function type, build a temporary `_Signature` from that type.
- Check argument count and types against the signature.
- Return the signature return type.
- Report an error when the value is not callable.

### 5.6 Pipelines

When a pipeline target is a function-typed value, treat the left value as the first argument and check the remaining arguments against the function type.

## 6. Runtime changes

### 6.1 Function value metadata

Extend `PowangFunction` in `src/powang_types.py` with:

- `function_type: str | None`.
- `captured_scopes: tuple | None`.
- `is_lambda: bool`.
- `mutable_capture: bool`.

Module functions keep the existing `closure` dictionary.

### 6.2 Lambda creation

In `_evaluateAstExpression`, handle `FUN_EXPRESSION` by creating a `PowangFunction`.

Capture behavior:

- By-value capture: copy the current scope lists and deep-copy variable values with `PowangCopyConstruct`.
- By-reference capture: save the live scope lists with `ScopeStack.save_scopes()`.
- Named lambda: after creation, bind the function in the captured function scope under its name.
- Method context: capture the current `this` value and make it available as `this` inside the lambda.

### 6.3 Calling lambdas

`callFunction` checks for `captured_scopes` before the module `closure` path.

When a lambda has captured scopes:

1. Save the caller scopes.
2. Restore the captured scopes.
3. Push a function scope.
4. Run the body.
5. Restore the caller scopes in `finally`.

The captured scopes are shared by every call to the same lambda value, which is what closure semantics require.

### 6.4 Assignment and copying

Add a special branch in `assignWithChecks` for `PowangFunction` targets. Copy the function fields from the right value instead of copying only `data`.

`PowangCopyConstruct` must preserve:

- `function_type`.
- `captured_scopes`.
- `is_lambda`.
- `mutable_capture`.

### 6.5 Undefined function values

`getUndefinedVariable` must handle a function type annotation. Create a `PowangFunction` placeholder with `defined=False` and the target `function_type`. The first assignment replaces it with the real lambda or function.

### 6.6 Casts and inspection

- Casting a function to a function type is accepted when the source is a function. If the source has a known `function_type`, check assignability.
- `typeof` returns `function`.
- `typedeep` returns `function_type` when available, otherwise `function`.

### 6.7 Task isolation

- By-value lambdas can be sent to a task. Their captured scopes are cloned for the task.
- Mutable-capture lambdas cannot be sent to a task. Reject them with a clear task error, consistent with the rule that references cannot cross task boundaries.

## 7. LSP changes

### 7.1 Grammar

Add TextMate rules for:

- `fun[` as a function type.
- `fun` followed by optional `&`, optional name and `(` as a lambda.
- Lambda parameter names and return types.
- The `&` mutable capture marker.

The function type rule must not be shadowed by the `fun` declaration rule.

### 7.2 Semantic tokens

- `fun` in a type is a keyword or builtin type.
- Lambda parameters are `parameter`.
- Function type brackets are operators.
- Function-typed variables keep their variable type in hover.

### 7.3 Hover and completion

- Hover on a function-typed variable shows `fun[...]`.
- Hover on a lambda shows its inferred function type.
- Completion adds a `fun[...]` snippet.
- Completion inside a lambda parameter list suggests parameter names and types.

## 8. Tests

### 8.1 Parser

- Function types in declarations, parameters, returns, arrays, maps, sets, tuples and unions.
- Nested function types.
- Lambda block bodies.
- Lambda expression bodies.
- Named lambdas.
- Mutable capture.
- Invalid function type with empty brackets.
- Lambda without a body.

### 8.2 Checker

- Assigning a declared function to a function-typed variable.
- Assigning a lambda to a function-typed variable.
- Wrong arity.
- Wrong parameter type.
- Wrong return type.
- Function type as a parameter.
- Function type as a return type.
- Function type inside a union.
- Calling a function-typed value.
- Lambda return inference.
- Named lambda recursion.
- Bare `function` annotation.

### 8.3 Runtime

- Lambda call.
- By-value capture.
- By-reference capture.
- Named recursion.
- Lambda returned from a function.
- Lambda stored in an array and called.
- Lambda in a pipeline.
- Lambda with default parameters.
- Lambda inside a method using `this`.
- Task rejection for mutable-capture lambdas.
- `typedeep` on a function.

### 8.4 LSP

- Function type highlighting.
- Lambda highlighting.
- Lambda parameter semantic tokens.
- Hover on a function-typed variable.
- Hover on a lambda.
- Completion snippet for `fun[...]`.

## 9. Commit sequence

| Commit | Objective |
|---|---|
| B1 | Add `TypeSpec` function kind and rendering. |
| B2 | Parse function type annotations. |
| B3 | Checker support for function type annotations and assignability. |
| B4 | Runtime placeholders and function assignment. |
| B5 | Parse lambda expressions. |
| B6 | Runtime lambda creation, closure capture and calls. |
| B7 | Checker lambda inference and function-typed calls. |
| B8 | Task isolation and function copying. |
| B9 | LSP grammar, semantic tokens, hover and snippets. |
| B10 | Documentation, version bump and release checks. |

## 10. Verification

From `C:\Users\zarap\Dev\Python\powang`:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -O -m unittest discover -s tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_function_types.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_lambdas.py" -v
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
| Function types become a fifth type representation | Build them on `TypeSpec` and use the rendered string only at boundaries |
| Closure capture breaks module closure behavior | Keep module `closure` and lambda `captured_scopes` separate |
| By-reference capture leaks across tasks | Reject mutable-capture lambdas at task boundaries |
| Checker string model cannot express function types | Add parse and render helpers in `typespec.py` and test round trips |
| Lambda parameter scoping leaks declarations | Push a dedicated lambda scope and pop in `finally` |
| Overloaded function values are ambiguous | Require a target function type to select an overload |
| LSP grammar shadows declarations | Put the lambda rule before the declaration rule and test both |

## 12. Acceptance criteria

- Function type annotations parse and render correctly.
- Declared functions and lambdas assign to function-typed variables.
- Function-typed parameters and returns check correctly.
- Lambdas call correctly with positional arguments.
- By-value capture does not observe later outer changes.
- By-reference capture mutates the outer variable.
- Named lambdas recurse.
- Lambdas survive after the defining scope returns.
- `typedeep` reports function signatures.
- Mutable-capture lambdas are rejected at task boundaries.
- LSP highlights function types and lambdas and shows their types.
- All existing tests pass in normal and `-O` modes.

## 13. Implementation outcome

Function types and lambdas are implemented:

- Function type annotations use `fun[arg_types..., ret_type]`.
- Lambdas support block bodies, `>>` bodies, named recursion and `fun &` mutable capture.
- Function values can be passed, returned and stored in arrays.
- Methods and static methods can be spawned as tasks.
- By-value capture snapshots the lexical scope. By-reference capture shares it.
- Lambdas capture `this` inside methods.
- Mutable-capture lambdas are rejected at task boundaries. By-value lambda captures are cloned for tasks.
- `typedeep` reports function signatures such as `fun[int, int]`.
- The LSP highlights function types and lambda parameters.
- Hover and completion documentation is plain text with no markdown bold or code spans.
- Examples cover loops, slicing, annotations, error frames, spawned methods, lambdas and function types.

Verification:

- powang: 291 tests pass in normal mode.
- powang: 291 tests pass under `python -O`.
- powang-lsp: 22 Python tests and 3 Node protocol tests pass.
- All examples run cleanly.
- LSP smoke, version, vendored source drift and VSIX inspection pass.
