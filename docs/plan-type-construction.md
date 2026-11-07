# Plan: Type Construction Syntax

Status: implemented in powang 0.8.0
Target: powang 0.8.0 (additive, backward compatible)
Related: user type system, constructors, access specifiers, match expressions

## 1. Goals

1. Make `Type.[args]` the official user type instantiation syntax.
2. Keep `.[args] as Type` valid but non-standard.
3. Support named constructor arguments `Type.[name >> value, ...]` with the
   all-or-nothing rule.
4. Add access defaults with `type T[+]` and `type T[-]`.
5. Allow members to omit access specifiers when the type has a default.
6. Warn when an access specifier is redundant with the type default.
7. Mark constructor participants with `|` and generate a member constructor
   from them.
8. Allow an explicit zero-parameter `constructor` body to run after the
   generated member assignments.
9. Reject the `const` keyword on `|` members, but allow `!` write-once const
   members as constructor parameters.
10. Provide inline constructor hints in `powang-lsp` and stay compatible with
    the `usernamehw.errorlens` extension.
11. Allow the same `.[...]` construction form on native types:
    `int.[2]`, `num.[2]`, `str.[2]`, `bool.[0]`, `arr.[2, 3]`,
    `tup[int, str].[2, "hi"]`, `tup.[2, 3.14, ""]`.
12. Infer structural element types, so `tup.[2, 3.14, ""]` is
    `tup[int, num, str]`, not `tup[any]`, and `arr.[2, 3, 4]` is
    `arr[int]`.
13. Treat `[1, 2, 3]`, `["a" >> 2]` and `.[1, 2]` as parser sugar for
    canonical construction.
14. Support union annotations such as `int | num` and `arr[int | num]`.
15. Add `typedeep`, while keeping `typeof` shallow.

## 2. Non-goals

- No inheritance.
- No generics beyond the existing `arr[T]` and `tup[...]`.
- No first-class type values such as `T := Point; T.[5]`.
- No keyword arguments on ordinary functions. Named arguments are constructor
  only for this release.
- No change to `error`, `fail`, `?`, or match semantics.

## 3. Final syntax specification

### 3.1 Type access defaults

```po
type PublicType[+] {
    id: int;         ## public by default
    - cache: int;    ## explicit private override
}

type PrivateType[-] {
    secret: str;     ## private by default
    + name: str;     ## explicit public override
}

type Legacy {
    + a: int;        ## explicit specifier required
    - b: int;
}
```

Rules:

| Declaration | Default access | Member without specifier |
|---|---|---|
| `type T[+]` | public | public |
| `type T[-]` | private | private |
| `type T` | none | error, specifier required |

A plain `type T` has **no implicit access level**. It is not public and not
private. Every member must declare `+` or `-` explicitly, exactly as today.

A member specifier that matches the type default is a warning, not an error:

```po
type T[+] {
    + name: str;   ## warning: unnecessary access specifier
}
```

### 3.2 Constructor members

`|` marks a member as a constructor parameter. It composes with the access
specifier.

| Form | Access | Constructor parameter |
|---|---|---|
| `name: str` | type default | no |
| `\| name: str` | type default | yes |
| `\| + name: str` | public | yes |
| `\| - name: str` | private | yes |
| `+ name: str` | public | no |
| `- name: str` | private | no |

Example:

```po
type Person[+] {
    id: int!;        ## public const, not a parameter
    | name: str;     ## public, parameter
    | address: str;  ## public, parameter
    age: num;        ## public, not a parameter
    - cache: int;    ## private, not a parameter
}
```

Generated constructor:

```po
+ fun constructor(name: str, address: str): Person {
    this.name = name;
    this.address = address;
    return this;
}
```

Rules:

- Parameters follow declaration order.
- Parameter names and types come from the member declaration.
- Body assigns `this.member = parameter` for each parameter.
- Constructor returns `this`.
- Constructor is always public.
- A type with no `|` members gets no generated constructor.

### 3.3 Instantiation

```po
p1 := Person.["Ada", "London"];                     ## positional, official
p2 := Person.[name >> "Ada", address >> "London"];  ## named, official
p3 := .["Ada", "London"] as Person;                  ## valid, non-standard
```

Rules:

- `Type.[...]` is a postfix form on a type name.
- `Type.[]` calls the zero-argument constructor.
- Named arguments use `identifier >> expression`.
- All-or-nothing: mixing positional and named is an error.
- Duplicate or unknown names are errors.
- Missing required parameters are errors.
- Named arguments are order independent.
- Legacy forms `[5] as Point` and `q: Point = 9` remain valid.

### 3.4 Native type construction

The `.[...]` form also constructs native values. The underlying type is the
name before the dot, optionally parameterized.

```po
i := int.[42];                  ## integer 42
n := num.[2];                   ## number 2.0
s := str.[25];                  ## string "25"
b := bool.[0];                  ## boolean false
a := arr.[2, 3, 4];             ## array [2, 3, 4], inferred arr[int]
w := arr[int | num].[2, 3.14];  ## union element type
t := tup.[2, 3.14, ""];         ## tuple (2, 3.14, ""), inferred tup[int, num, str]
u := tup[int, str].[2, "hi"];   ## typed tuple, element checks applied
v := arr[int].[2, 3, 4];        ## typed array, element checks applied
m := map.["a" >> 1, "b" >> 2];  ## map construction
```

Rules:

- Scalar construction follows the explicit cast rules. `int.[2.5]` truncates,
  `str.[25]` yields `"25"`, `bool.[0]` yields `false`.
- Invalid combinations raise the same errors as explicit casts.
- `arr.[...]` without a type parameter infers the element type from the
  arguments. If the arguments disagree, the inferred element type is a union
  such as `int | num`, not `some`.
- `tup.[...]` without a type parameter infers one type per position.
- Only genuinely unknown element types degrade to `some`.
- `arr[T].[...]` and `tup[T1, T2, ...].[...]` are typed constructions. Each
  argument must be assignable to its element type, by the normal assignability
  rules.
- Typed construction applies the same implicit casts as a typed declaration.
- Arity must match exactly for tuples and typed construction.
- `map.[...]` constructs a map from `key >> value` entries. A map literal
  `["a" >> 2]` is sugar for it. Duplicate keys keep the last value. Keys must
  be hashable. Named constructor arguments do not apply to `map`.
- Parser desugaring happens in the parsing layer. The runtime only sees
  canonical construction nodes, plus the `auto` placeholder that the checker
  resolves to an inferred union.

Literal sugar:

| Sugar | Desugars to | Inferred type |
|---|---|---|
| `[1, 2, 3]` | `arr[int].[1, 2, 3]` | `arr[int]` |
| `[2, 3.14]` | `arr[int \| num].[2, 3.14]` | `arr[int \| num]` |
| `["a" >> 2]` | `map.["a" >> 2]` | `map` |
| `.[2, 3.14, ""]` | `tup[int, num, str].[2, 3.14, ""]` | `tup[int, num, str]` |

A plain `[...]` literal containing any `>>` pair desugars to `map.[...]`.
Otherwise it desugars to `arr[auto].[...]`. A plain `.[...]` literal desugars
to `tup[auto, ...].[...]`.

Inference rules:

| Expression | Inferred type |
|---|---|
| `int.[42]` | `int` |
| `num.[2]` | `num` |
| `str.[25]` | `str` |
| `bool.[0]` | `bool` |
| `arr.[2, 3, 4]` | `arr[int]` |
| `arr.[2, 3.14]` | `arr[int \| num]` |
| `[2, 3.14]` | `arr[int \| num]` |
| `tup.[2, 3.14, ""]` | `tup[int, num, str]` |
| `.[2, 3.14, ""]` | `tup[int, num, str]` |
| `tup[int, str].[2, "hi"]` | `tup[int, str]` |
| `tup[int, str].[2, 3]` | type error, second element is `int` not `str` |
| `map.["a" >> 2]` | `map` |

Disambiguation rules:

- `Name.[...]` is always construction.
- `Name[T, ...].[...]` is parameterized construction only when `Name` is a
  built-in generic type (`arr`, `tup`) or a type name known to the parser.
- `x[0]` without a following `.[` remains index access.
- A variable named `arr` still supports `arr[0]` as indexing. The parser uses
  lookahead and backtracks when `.[...]` does not follow.

### 3.5 Union type annotations

A union annotation accepts a value assignable to any branch.

```po
x: int | num = 2;              ## accepted
y: int | num = 2.5;            ## accepted
z: arr[int | num] = [1, 2.5];  ## accepted, mixed array
n: int | str = 3;              ## accepted
m: int | str = 3.14;           ## rejected
```

Rules:

- `A | B | C` accepts a value assignable to `A`, `B` or `C`.
- A union source is assignable to a single target only when every branch is
  assignable to that target.
- Nesting flattens. `int | (str | num)` becomes `int | str | num`.
- Duplicate branches collapse.
- Qualifiers apply to the whole union. `@(int | str)` is weak and accepts
  `nova`. `(int | str)!` is a const union.
- Constructors, parameters and return types may use unions.
- Runtime values do not change. A value keeps its own concrete type. The union
  only decides assignability.
- Casting to a union tries each branch in order and uses the first successful
  cast.
- Overload scoring matches a union parameter when the argument matches any
  branch, scored with the best branch.
- `::` with a union is true when the value matches any branch.
- Container unions such as `array | map` do not merge operations. The concrete
  type still decides operators.

### 3.6 Explicit constructor body hook

An explicit public constructor with no parameters is treated as a body hook for
the generated member constructor.

```po
type Person[+] {
    | name: str;
    | address: str;

    + fun constructor {
        if name == "" {
            error("name is required");
        }
    }
}
```

Semantics:

1. The compiler infers the parameter list from the `|` members, in declaration
   order, exactly as if the constructor had been generated.
2. It emits the ghost assignments first:
   `this.name = name; this.address = address;`.
3. It then runs the author's body.
4. It returns `this` at the end.

If the type has no `|` members, `+ fun constructor {}` is an ordinary
zero-parameter constructor and no ghost assignments are emitted. The empty
parentheses are optional, so `+ fun constructor {` and `+ fun constructor() {`
are equivalent.

If the explicit constructor declares parameters, it is treated as a normal
constructor and the user is responsible for assignments. It suppresses the
generated one, with a warning when `|` members are present.

### 3.7 Constant members and `|`

There are two constant forms, with different constructor rules:

| Member form | With `\|` | Behaviour |
|---|---|---|
| `const name: str` | rejected | The `const` keyword is not a constructor parameter |
| `name: str!` | allowed | Write-once initialization from the constructor |
| `\| name: str!` | allowed | Write-once initialization from the parameter |

`!` constants already carry an undefined state and become defined after their
first assignment. A constructor assignment is exactly that single
initialization. A second assignment still raises the const error.

`const` keyword members are rejected with `|` because that form declares an
already-initialized constant, which a constructor cannot rewrite.

### 3.8 Proposed decisions to confirm

| Decision | Proposal |
|---|---|
| Explicit constructor plus `\|` members | A zero-parameter explicit constructor becomes a body hook, see 3.5. A constructor with parameters suppresses generation and warns about ignored `\|` members. |
| `\|` on a `const` keyword member | Reject with a clean error. |
| `\|` on a `!` const member | Allow, treated as single initialization. |
| `-` inside `type T[-]` | Same warning as `+` inside `type T[+]`. |
| Named argument order | Order independent, matched by name. |
| Named arguments on legacy `as` casts | Not supported in v1. `.[...] as T` is positional only. |
| Plain `type T` with omitted specifier | Error, preserving current behavior. |
| Duplicate `\|` parameter names | Redefinition error at declaration. |
| Member initializer plus `\|` | Initializer runs first, constructor assignment overrides it, except `!` constants which accept exactly one write. |

## 4. Grammar changes

```text
TypeDeclaration := "type" Identifier AccessDefault? "{" Member* "}"
AccessDefault   := "[" ("+" | "-") "]"

Member          := Pipe? Access? MemberBody
Pipe            := "|"
Access          := "+" | "-"
MemberBody      := Identifier ":" Type ("=" Expression)?
                 | "fun" Identifier ParameterList? ("->" | ":")? Type? Block
                 | "fun" "constructor" Block
ParameterList   := "(" (Parameter ("," Parameter)*)? ")"

Type            := UnionType
UnionType       := PrimaryType ("|" PrimaryType)*
PrimaryType     := Identifier TypeParameters? Weak? Const?

Instantiation   := TypeRef "." "[" ArgumentList? "]"
TypeRef         := Identifier TypeParameters?
TypeParameters  := "[" (Type ("," Type)*)? "]"
ArgumentList    := Positional ("," Positional)*
                 | Named ("," Named)*
Named           := Identifier ">>" Expression
```

Literal sugar, applied in the parser:

```text
[1, 2, 3]          => arr[auto].[1, 2, 3]
[2, 3.14]          => arr[auto].[2, 3.14]      ## auto resolves to int | num
["a" >> 2]         => map.["a" >> 2]
.[2, 3.14]         => tup[auto, auto].[2, 3.14]
```

`auto` is a placeholder type that the checker replaces with the inferred
element type. The runtime never sees `auto` after checking.

Token notes:

- `[+]` currently lexes as OPERATOR_SUMATORY and `[-]` as OPERATOR_INVERSE.
  Reuse these tokens in type declaration context instead of adding new ones.
- Add a single `|` token. `||` must be matched first so logical or is unaffected.
- `.[` is DOT followed by LEFT_BRACKET. The parser decides between tuple
  literal and instantiation from context.
- `++` and `--` are no longer used for constructor members. Keep them as
  ordinary unary or arithmetic tokens.
- A constructor may omit its parameter list entirely, as in
  `+ fun constructor { ... }`. The parser treats a missing `(` before the body
  as a zero-parameter constructor.
- `arr[...]` and `tup[...]` are ambiguous with index access only when they are
  not followed by `.[`. Parse them as type references with lookahead and
  backtrack to index access when no `.[` follows.

## 5. AST changes

Type declaration node gains:

- `access_default`: `"+"`, `"-"`, or `None`.
- Each property entry gains `constructor_member: bool` and `explicit_access:
  "+"`, `"-"`, or `None`.

New nodes:

- `TYPE_REFERENCE`: `{ "name": identifier, "type_parameters": [Type] }`.
- `INSTANTIATION`: `{ "type_ref": TYPE_REFERENCE, "arguments": [...],
  "named": bool }`.
- Each argument: `{ "name": Optional[identifier], "value": expression }`.

`TYPE` nodes gain:

- `alternatives`: a list of type nodes for unions. A single type has one
  alternative.
- `auto`: true for the placeholder generated by literal sugar.
- `typedeep` metadata is computed from the same node when the checker
  resolves the type.

## 6. Runtime changes

### 6.1 Type declaration

1. Resolve each member's effective access:
   explicit specifier, else type default, else error.
2. Emit a warning when an explicit specifier equals the default.
3. Collect constructor members in declaration order.
4. Build the type template as today.
5. If there is at least one constructor member and no explicit `constructor`,
   synthesize the constructor function and register it as an overload.
6. If an explicit constructor exists, skip generation and warn about ignored
   constructor members.

### 6.2 Constructor synthesis

Build a `PowangFunction` whose args are generated declarations and whose body
is a synthesized block:

```text
this.member = parameter;
...
return this;
```

Use the existing declaration and return AST shapes so method dispatch,
`this` resolution and return checking keep working unchanged.

### 6.3 Instantiation

1. Resolve the type name in the active scope's user types.
2. Evaluate all arguments in the caller scope.
3. Positional form: select an overload by arity and argument types, reusing
   `getFunctionCandidate`.
4. Named form: map each name to a constructor parameter, reorder to the
   parameter order, reject duplicates, unknown names and missing required
   parameters, then dispatch.
5. Call the constructor through `callMethod` and return the instance.

### 6.4 `.[...] as Type`

1. Keep the existing tuple literal parsing.
2. Extend the `as` cast path: when the left value is a tuple and the right is
   a user type, treat the tuple elements as positional constructor arguments.
3. Reject named pairs inside this form with a clear error.

### 6.5 Warnings

Add a warning sink to the interpreter state. Warnings print to stderr as
`[WARNING] message` and never change the exit code. `--no-warnings` disables
them. The REPL prints warnings but continues.

### 6.6 Explicit zero-parameter constructor hook

1. At type declaration time, detect a public constructor with no declared
   parameters.
2. If the type has `|` members, synthesize the parameter list from them and
   prepend the ghost assignments to the author's block.
3. If the type has no `|` members, leave the constructor unchanged.
4. If a public constructor declares parameters, treat it as a normal
   constructor and suppress generation, warning about unused `|` members.

### 6.7 Constant member rules

1. Reject `const` keyword members combined with `|`, with a clean diagnostic.
2. Allow `!` constants with `|`. The ghost assignment is the single write that
   moves the constant from undefined to defined.
3. A second assignment still raises the const error.
4. Named arguments map to the same write-once parameter.

### 6.8 Native type construction

1. Resolve the type reference: a native name (`int`, `num`, `str`, `bool`,
   `nova`, `arr`, `tup`) or a parameterized form (`arr[T]`, `tup[T, ...]`).
2. Evaluate arguments in the caller scope.
3. Scalar construction delegates to the explicit cast helper.
4. `arr.[...]` creates a `PowangArray` from the evaluated elements.
5. `tup.[...]` creates a `PowangTuple` from the evaluated elements.
6. Typed `arr[T].[...]` and `tup[T...].[...]` check each argument against its
   element type before construction, using the normal assignment checks.
7. Typed construction rejects arity mismatches for tuples with a clear error.
8. Named arguments are rejected for native construction. Only user type
   constructors accept names.

### 6.9 Union runtime checks

1. `assignWithChecks` accepts a value when it is assignable to any branch.
2. A union source is assignable to a single target only when every branch is
   assignable to that target.
3. No wrapper value is introduced. The value keeps its concrete type.
4. `getUndefinedVariable` builds a default from the first branch, and the
   value stays undefined until assignment.
5. Casting to a union tries each branch in order and returns the first
   successful cast.

### 6.10 `typedeep` builtin

`typedeep(value)` returns the structural type of a value.

```po
typedeep(tup.[2, 3.14])   ## "tup[int, num]"
typedeep([1, 2.5])        ## "arr[int | num]"
typedeep(7)               ## "int"
typedeep(Point.[1, 2])    ## "Point"
```

Rules:

- Scalars return their type name: `int`, `num`, `str`, `bool`, `nova`.
- Arrays return `arr[T]`, using the inferred element type, including unions.
- Tuples return `tup[T1, T2, ...]`.
- Maps return `map`.
- User types return their declared type name without members.
- `typeof` remains shallow and returns `arr`, `tup`, `map`, `int`, `num`,
  `str`, `bool`, `nova`, or the user type name.

## 7. Type checker changes

1. Recognize `INSTANTIATION` and infer `object:TypeName`.
2. Validate positional arity against constructor signatures.
3. Validate named arguments: all-or-nothing, known names, duplicates, missing
   required names, parameter type compatibility.
4. Register generated constructor signatures when checking a type declaration.
5. Surface declaration warnings through the same warning sink.
6. Degrade to `some` when the constructor signature cannot be resolved.
7. Infer native construction types:
   - `int.[e]` is `int`, `num.[e]` is `num`, `str.[e]` is `str`,
     `bool.[e]` is `bool`, `nova.[]` is `nova`.
   - `arr.[a, b, ...]` is `arr[T]` when all elements share a common type,
     otherwise `arr[T1 | T2 | ...]`, never `arr[any]`.
   - `tup.[a, b, ...]` is `tup[T1, T2, ...]` with one inferred type per
     position.
8. Check typed construction:
   - `arr[T].[...]` checks every element against `T`.
   - `tup[T1, ...].[...]` checks each position and the exact arity.
   - Implicit casts follow the declaration rules.
9. Reject named arguments for native construction.
10. Never widen an inferred tuple to `tup[any]`. Use `some` only for genuinely
    unknown element types.
11. Implement union assignability: target union accepts any branch, source
    union to single target requires every branch to be assignable.
12. Flatten and deduplicate union branches during checking.
13. Resolve the `auto` placeholder from literal sugar into the inferred union
    or structural type.
14. Compute `typedeep` results from the resolved structural type.

## 8. Step-by-step implementation

### Phase 0: Tokens and parser scaffolding

- W1. Add single `|` lexer token after `||`, before `|`-free operators.
  Acceptance: `a | b` tokenizes as PIPE, `a || b` still tokenizes as OR.
  Verify: tokenizer unit test.
- W2. Parse the optional access default after `type Name`.
  Acceptance: `type T[+]` and `type T[-]` produce `access_default`.
  Verify: parser fixtures.
- W3. Parse optional `|` and optional access per member. Track
  `constructor_member` and `explicit_access`.
  Acceptance: all six member forms from section 3.2 parse.
  Verify: parser fixture matrix.
- W3a. Accept `fun constructor` without parentheses before its block.
  Acceptance: `+ fun constructor { ... }` and `+ fun constructor() { ... }`
  produce the same AST.
  Verify: parser fixture pair.
- W4. Add a parser warning list and emit redundant specifier warnings.
  Acceptance: no warning for valid forms, exactly one warning for redundant
  forms.
  Verify: parser warning test.
- W5. Parse `Type.[args]` as INSTANTIATION in postfix position.
  Acceptance: `Point.[5, 7]`, `Point.[]` and `Point.[x >> 1]` parse.
  Verify: parser fixtures.
- W6. Enforce all-or-nothing at parse time and reject mixing.
  Acceptance: mixed form produces a syntax error naming the rule.
  Verify: negative fixtures.
- W7. Normalize the type declaration AST shape and keep
  `simulate_Type` and module export paths consistent.

### Phase 1: Runtime type declaration

- W8. Resolve effective access and emit redundant warnings.
- W9. Synthesize the member constructor and register it.
  Acceptance: the Person example produces `constructor(name, address)`.
  Verify: inspect `getConstructors()` and call it.
- W10. Handle explicit constructor coexistence, including the warning about
  ignored `|` members.
- W11. Reject `!` constants? No: reject `const` keyword members with `|`, and
  allow `!` constants with `|` as single initialization.
  Acceptance: `const x` plus `|` errors. `| x: int!` is accepted once.
  Verify: runtime fixtures for both.
- W11a. Implement the zero-parameter constructor hook: infer the parameter list
  from `|` members, prepend the ghost assignments, then run the author block.
  Acceptance: `+ fun constructor { ... }` receives `name` and `address` and
  runs after `this.name = name; this.address = address;`.
  Verify: constructor with a failing validation and a passing validation.

### Phase 2: Instantiation runtime

- W12. Positional instantiation, including zero arguments and overload
  selection.
- W13. Named instantiation, with reordering and the all-or-nothing check.
- W14. `.[...] as Type` positional route.
- W15. Clear errors for unknown type, unknown name, duplicate name, missing
  name, wrong arity and wrong types.
- W15a. Native scalar construction: `int.[2]`, `num.[2]`, `str.[2]`,
  `bool.[0]`, `nova.[]`, delegating to the cast rules.
  Acceptance: values and errors match explicit casts.
  Verify: cast fixtures.
- W15b. Native container construction: `arr.[...]`, `tup.[...]`,
  `arr[T].[...]`, `tup[T, ...].[...]`.
  Acceptance: runtime values carry the expected element data.
  Verify: array and tuple fixtures.
- W15c. Typed construction checks: element assignability and exact tuple
  arity, with clean diagnostics.
  Acceptance: `tup[int, str].[2, 3]` fails, `tup[int, str].[2, "hi"]` passes.
  Verify: negative and positive fixtures.
- W15d. Parser disambiguation for `arr[...]` and `tup[...]` between index
  access and type references, using lookahead and backtracking.
  Acceptance: `arr[0]` stays index access, `arr.[1, 2]` is construction,
  `tup[int, str].[...]` is parameterized construction.
  Verify: parser fixtures.
- W15e. Parser desugaring for literals: array literals, map pair literals and
  tuple literals become canonical INSTANTIATION nodes with `auto`
  placeholders. Acceptance: the AST is identical for `[1, 2]` and
  `arr.[1, 2]` after the checker resolves `auto`.
  Verify: AST comparison fixtures.
- W15f. Map construction `map.[key >> value, ...]`, including duplicate keys
  and hashability errors. Acceptance: entries appear in insertion order and
  the last duplicate wins.
  Verify: map fixtures.

### Phase 3: Type checker

- W16. Infer `object:TypeName` from INSTANTIATION.
- W17. Validate named and positional constructor arguments.
- W18. Register generated constructors for checking.
- W19. Emit declaration warnings through the sink.
- W19a. Infer native construction types and structural element types:
  `int.[2]` is `int`, `arr.[2, 3]` is `arr[int]`, `tup.[2, 3.14, ""]` is
  `tup[int, num, str]`.
  Acceptance: inferred types are visible to the checker and never degrade to
  `tup[any]`.
  Verify: checker fixtures.
- W19b. Check typed construction and native construction errors.
  Acceptance: invalid element type and arity are rejected before execution.
  Verify: negative fixtures.
- W19c. Implement union assignability, flattening, deduplication and cast
  order. Acceptance: `int | num` accepts both, `int | str` rejects `num`.
  Verify: checker fixtures.
- W19d. Implement `typedeep` type computation and register the builtin.
  Acceptance: `typedeep(tup.[2, 3.14])` is `tup[int, num]` and `typeof` stays
  `tup`.
  Verify: builtin fixtures.

### Phase 4: Diagnostics and CLI

- W20. Warning printer and `InterpreterState.warnings`.
- W21. `--no-warnings` flag.
- W22. REPL behavior and exit code invariance.

### Phase 5: Tests

- W23. Parser tests for access defaults, `|`, named args and mixing errors.
- W24. Runtime tests for generated constructors, positional and named forms.
- W25. Type checker tests for valid and invalid instantiations.
- W26. Warning tests for redundant specifiers and ignored `|` members.
- W27. Full regression suite, all examples, `--check`, `python -O`.
- W27a. Native construction tests: scalars, arrays, tuples, typed forms,
  inference, mixed arrays, arity errors and parser disambiguation.
  Verify: fixtures for each acceptance line in section 9.

### Phase 6: Docs, examples and versioning

- W28. `examples/type-construction.po` with positional, named, `as`, `|`, and
  hook forms.
- W29. README syntax section and CHANGELOG entry.
- W30. Version bumps: powang 0.5.2, powang-lsp 0.8.2.
- W31. Final verification and commit in both repositories.

### Phase 7: LSP inline suggestions and ErrorLens

- W32. Add line and column positions to tokens and to `PowangError`. This is a
  prerequisite for precise diagnostics. Acceptance: a syntax error underlines
  the offending token, not the start of the file.
- W33. Inlay hints for constructor calls. Show the parameter name before each
  positional argument, for example `Person.[name: "Ada", address: "London"]`.
  Suppress hints when named arguments are already used. Acceptance: hints
  appear only for user type instantiations.
- W34. Inline completion suggestions inside type bodies. Suggest `|` for
  constructor members, `[+]` and `[-]` after a type name, and `constructor`
  after `fun`. Acceptance: suggestions appear at the right syntactic
  positions and never inside strings or comments.
- W35. Code actions. Offer "Convert to named arguments", "Make public", "Make
  private", and "Add missing constructor argument". Acceptance: each action
  produces valid code and a clean re-diagnose.
- W36. ErrorLens compatibility. ErrorLens reads standard VS Code diagnostics,
  so the server must:
  1. Publish `textDocument/publishDiagnostics` on open, change, save and
     close, with a precise `range`.
  2. Set `source` to `powang` and `code` to the error kind.
  3. Use `relatedInformation` for constructor parameter hints.
  4. Never send diagnostics through stderr only.
  Acceptance: ErrorLens renders every warning and error inline, with no
  custom decorations and no duplicated text.
- W37. LSP tests and rebuild. Add fixtures for hints, completions, code
  actions and diagnostics, run the smoke harness, bundle `src/`, rebuild the
  VSIX, and verify the extension still starts with the bundled server.

## 9. Acceptance criteria

- `Person.["Ada", "London"]` creates a Person.
- `Person.[name >> "Ada", address >> "London"]` creates the same Person.
- `.["Ada", "London"] as Person` creates the same Person.
- `Person.["Ada"]` fails with a missing argument diagnostic.
- `Person.["Ada", address >> "London"]` fails with the all-or-nothing rule.
- `type T[+] { x: int; }` creates a public member.
- `type T[+] { + x: int; }` warns about the redundant specifier.
- `type T[-] { | x: int; }` creates a private constructor parameter.
- `type T { x: int; }` fails because a plain type has no default access.
- `|` with a `const` keyword member is rejected.
- `| x: int!` is accepted and the constructor performs the single write.
- A window calling `Person.["Ada"]` shows the missing parameter diagnostic.
- `+ fun constructor { ... }` receives the `|` parameters and runs after the
  ghost assignments.
- `int.[42]` yields `42`, `num.[2]` yields `2.0`, `str.[25]` yields `"25"`,
  `bool.[0]` yields `false`.
- `arr.[2, 3, 4]` yields `[2, 3, 4]` typed `arr[int]`.
- `tup.[2, 3.14, ""]` yields a tuple typed `tup[int, num, str]`.
- `tup[int, str].[2, "hi"]` passes, and `tup[int, str].[2, 3]` fails.
- `arr.[2, 3.14]` is `arr[int | num]`, not `arr[some]` and not `arr[any]`.
- `[1, 2, 3]` and `arr[int].[1, 2, 3]` are equivalent after desugaring.
- `["a" >> 2]` and `map.["a" >> 2]` are equivalent after desugaring.
- `.[2, 3.14]` and `tup[int, num].[2, 3.14]` are equivalent after desugaring.
- `arr[0]` remains index access, and `arr.[1, 2]` is construction.
- `x: int | num = 2` and `x = 2.5` are accepted, `x: int | str = 2.5` is
  rejected.
- `typedeep(tup.[2, 3.14])` returns `"tup[int, num]"`.
- `typedeep([1, 2.5])` returns `"arr[int | num]"`.
- `typeof(tup.[2, 3.14])` stays `"tup"`.
- LSP inlay hints show parameter names for positional constructor calls.
- ErrorLens renders powang diagnostics inline with correct ranges.
- All existing examples and tests pass unchanged.
- `--check` accepts the new syntax and reports invalid instantiations.

## 10. Verification commands

```bash
python -m unittest discover -s tests
python powang.py examples/type-construction.po
python powang.py --check examples/type-construction.po
python powang.py --no-warnings examples/type-construction.po
python -O powang.py examples/functions.po
```

In `powang-lsp`, after syncing `src/`:

```bash
python lsp_smoke.py
vsce package
```

## 11. Risks and mitigations

| Risk | Mitigation |
|---|---|
| `[+]` token conflict with the unary summatory operator | Parse it only after `type Name` |
| `.[` ambiguity between tuple literal and instantiation | Decide from position, type name followed by `.[`, not a bare tuple |
| Named arguments with overloads | Disambiguate by name set first, then arity and types |
| Constructor parameter order stability | Declaration order, documented and tested |
| Private constructor parameters exposed in a public signature | Document explicitly, test |
| Redundant warnings flooding output | One line per declaration, `--no-warnings` |
| Generated constructor and explicit constructor drift | Explicit constructor always wins, warning emitted |
| Zero-parameter hook receives inferred parameters in a surprising order | Document declaration order and show it in hover |
| Diagnostics without ranges break ErrorLens output | Add token positions first, W32 blocks W36 |
| Inlay hints on every positional call add noise | Only user type instantiations, never builtins or legacy casts |
| LSP semantic tokens missing `\|` | Add the token and rebuild the VSIX |
| `arr[0]` versus `arr.[...]` ambiguity | Lookahead and backtrack, W15d |
| Inferred tuple types drifting to `some` | Per-position inference, never `tup[any]` |
| Mixed arrays producing surprising types | Infer a union of element types, documented |
| Union annotations making overload scoring ambiguous | Score with the best branch, test ties |
| Native construction bypassing cast rules | Delegate to the same cast helpers |

## 12. Open questions for review

1. Should the generated constructor be an overload when an explicit
   constructor with a different signature exists, instead of being suppressed.
2. Should named arguments also work on legacy `.[...] as Type`.
3. Should redundant specifier warnings be errors under a future `--strict`.
4. Should inline completions suggest the full `| name: str;` member template
   or only the `|` marker.
5. Should ErrorLens receive a separate `relatedInformation` entry for every
   constructor parameter, or only for missing ones.
6. Should `typedeep` also print weak and const qualifiers, for example
   `@int` or `int!`, or only the structural name.
