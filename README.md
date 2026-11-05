# powang: The multi-purpose programming language written by me :D.

![powang banner](./assets/powang_banner.jpeg)

> [!WARNING]
> It's still work in progress so expect to encounter bugs or undefined behaviours.

Hiii, this is POLA, a software engineering student, and this is my own programming language.
Initially based on the lisp operators but later changed into a more natural language.

## Examples

| File | Shows |
|---|---|
| [`examples/variables.po`](examples/variables.po) | declarations, weak types, constants |
| [`examples/arithmetics.po`](examples/arithmetics.po) | operators, casting, arrays and strings |
| [`examples/functions.po`](examples/functions.po) | functions and overloads |
| [`examples/control-flow.po`](examples/control-flow.po) | if/else, loops, for-each, try/catch/finally |
| [`examples/errors.po`](examples/errors.po) | raising, catching, error unions and `?` |
| [`examples/types.po`](examples/types.po) | user types, constructors, methods, privacy |
| [`examples/collections.po`](examples/collections.po) | typed arrays, maps, strings, `%` and exponent literals |
| [`examples/modules.po`](examples/modules.po) | module namespaces, aliases and wildcard imports |
| [`examples/stdlib.po`](examples/stdlib.po) | strings, json, url and crypto |
| [`examples/tasks.po`](examples/tasks.po) | spawn and wait |
| [`examples/references.po`](examples/references.po) | reference parameters that mutate the caller |
| [`examples/modern.po`](examples/modern.po) | interpolation, destructuring, match, ranges and pipelines |

## References

A parameter declared `&type` receives a reference to a variable, and the caller passes
`&variable`. Reads and writes inside the function reach the caller's variable:

```po
fun increment(value: &integer) {
    value += 1;
}

x := 10;
increment(&x);
print(x);        ## 11
```

Rules:

- References are explicit at the call site: `increment(&x)`, not `increment(x)`.
- Only variables can be referenced. Constants are rejected.
- A reference lives for one call. It cannot be stored, returned, or sent to a task.
- Arguments are still evaluated in the caller, and the parameter's operations use the
  normal type checks.

## Typed arrays

Array annotations accept an element type:

```po
numbers: array[integer] = [1 2 3];
names: array[string] = ["ada" "grace"];
```

A bare `array` is sugar for `array[any]`, which accepts any element type:

```po
values: array = [1 "two" true];
```

Element types are checked on declarations, function arguments and return values.
Typed annotations also work in casts, for example `values as array[integer]`.
The runtime representation is still one `array` type, so typed arrays add no runtime cost.

## Output and input

- `print(...)` writes each argument without adding a newline and returns the argument count.
- `println(...)` writes each argument and then a newline.
- `format(template, ...)` returns a formatted string with `{0}`, `{1}` and `{n/separator}` placeholders.
- `printf(template, ...)` formats and prints in one call.
- `input(receptor)` reads one line into `receptor`.
- `inputf(receptor, prompt)` prints `prompt` and then reads one line into `receptor`.

## Comments and strings

Line comments use `##`. Block comments use `#! ... !#`.

```po
## line comment

#!
This comment can span
more than one line.
!#
```

Strings support interpolation with `$"..."`:

```po
name := "Ada";
println($"Hello, {name}! 2 + 2 = {2 + 2}");
```

Use `{{` and `}}` for literal braces inside an interpolated string.

## Collections and iteration

Trailing commas are allowed in arrays, maps, calls and parameters. Arrays accept commas:

```po
numbers := [1, 2, 3,];
pairs := ["name" >> "powang", "kind" >> "language",];
```

Ranges use two or three `>>` parts after the iterator. The end is exclusive.

```po
for i >> 0 >> 3 { print(i); }          ## 0, 1, 2
for i >> 0 >> 2 >> 10 { print(i); }    ## 0, 2, 4, 6, 8
```

Destructuring works for arrays and objects with the same bracket syntax:

```po
[a, b] := pair;
[a: integer, b] := pair;
[a, b]: integer = pair;
[r:&, s] := pair;    ## r references pair[0]
```

For each supports destructuring directly:

```po
for [key, value] >> pairs { println($"{key}={value}"); }
for [key: string, value: integer] >> pairs { println($"{key}:{value}"); }
```

## Pattern matching

```po
match value {
    case 0 >> print("zero");
    case n if n < 0 >> print("negative");
    case _ >> print("positive");
}
```

Patterns support literals, identifier bindings, typed bindings, wildcards and guards.

## Null safety

`?.` short-circuits on `nova`. `??` supplies a fallback.

```po
name := user?.name ?? "anonymous";
```

A declaration in an `if` condition is scoped to the block and uses `nova` as falsey:

```po
if name := user?.name {
    println($"Hello, {name}!");
}
```

## Functions

Expression-bodied functions use `>>`:

```po
fun double(x: integer): integer >> x * 2;
```

Named arguments use `>>`:

```po
fun greet(name: string = "world") {
    println($"Hello, {name}!");
}

greet(name >> "Ada");
```

Pipelines pass the left value as the first argument:

```po
result := "  powang  " |> strings.trim |> strings.upper;
```

## Constants

`const` creates a compile-time macro that is substituted everywhere it appears.

```po
const MAX_SIZE: integer = 1024;
const DOUBLE_MAX = MAX_SIZE * 2;
```

`!` marks a runtime immutable value. It still occupies memory and can be passed around.

```po
buffer_size: integer! = 64;
```

## Get started
You need [Python3](https://www.python.org/) 3.12 or newer.

- Clone the repository with:
```git clone https://github.com/POLA-LCS/powang```

- Go to `./powang`
- Run `python powang.py --help`
- Create the file `main.po`
- Write your first hello world with `print("Hello, world!\n");`
- Run it with `python powang.py main.po`
