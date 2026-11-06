# powang

A small hand-written, multi-purpose programming language interpreter written in Python.

![powang banner](./assets/powang_banner.jpeg)

> [!WARNING]
> powang is still work in progress, so expect bugs or undefined behaviour.

## Quick start

You need Python 3.12 or newer.

```sh
git clone https://github.com/POLA-LCS/powang
cd powang
python powang.py --help
```

Create a file named `main.po`:

```po
print("Hello, world!\n");
```

Run it:

```sh
python powang.py main.po
```

Start the interactive REPL by running `python powang.py` with no arguments.

## Language at a glance

```po
use strings;

const MAX_SCORE: int = 100;

fun classify(value: int): str {
    match value {
        case 0 >> return "zero";
        case n if n < 0 >> return "negative";
        case _ >> return "positive";
    }
}

numbers := [1, 2, 3,];
pairs := ["a" >> 1, "b" >> 2,];

for [key: str, value: int] >> pairs {
    println($"{key}={value}");
}

result := "  powang  " :> strings.trim :> strings.upper;
println(result);
println(classify(-3));
```

## Core concepts

### Types

powang is gradually typed. Annotated declarations, assignments, operators, calls and returns are checked. Unannotated code stays dynamic and degrades to `some`.

Built-in types: `int`, `num`, `str`, `boolean`, `arr`, `map`, `tup`, `some`, `nova`, `file`, `task`, `function`, `error`, `module`, `object`, `reference`.

```po
undefined_variable: int;
defined_variable: str = "Holaaa";
infered_variable := [10, 20, 30];

integer_variable: int = 2.5;          ## truncates to int
number_variable: num = 2;
string_variable: str = 25 as str;

weak_variable: @str = nova;          ## weak type holds str or nova
weak_variable = "Holaaa";
weak_variable = nova;
```

Typed arrays accept an element type. A bare `arr` is sugar for `arr[any]`.

```po
numbers: arr[int] = [10 20 30];
mixed: arr = [1 "two" true];         ## arr[any]
typed_names: arr[str] = ["ada" "grace"];
```

Element types are checked on declarations, function arguments, return values, indexing and casts. Typed annotations also work in casts, for example `values as arr[int]`. The runtime representation is still one `arr` type, so typed arrays add no runtime cost.

### Control flow

```po
fun classify(value: int): str {
    if value < 0 {
        return "negative";
    } else if value == 0 {
        return "zero";
    } else {
        return "positive";
    }
}

for index := 0; index < 3; index += 1 {
    print(index);
    print(" ");
}

numbers := [10 20 30];
for num: int >> numbers {
    print(num);
    print(" ");
}

## Filtered iteration
for num >> numbers if num > 15 {
    print(num);
    print(" ");
}
```

Strings and maps are iterable. Ranges use two or three `>>` parts after the iterator and the end is exclusive.

```po
for i >> 0 >> 3 { print(i); }          ## 0, 1, 2
for i >> 0 >> 2 >> 10 { print(i); }    ## 0, 2, 4, 6, 8
```

try, catch and finally:

```po
fun divide(a: int, b: int): int {
    try {
        if b == 0 {
            error("division by zero");
        }
        return a / b;
    } catch problem {
        print("caught " + problem.kind + ": " + problem.message + "\n");
        return 0;
    } finally {
        print("cleanup\n");
    }
}
```

### Functions

```po
fun add(left: int, right: int): int {
    return left + right;
}

## Expression-bodied function
fun double(x: int): int >> x * 2;

## Default arguments and named arguments
fun greet(name: str = "world", punctuation: str = "!"): str >> $"Hello, {name}{punctuation}";

greet();
greet(name >> "Ada");
```

Overload resolution picks the best matching signature.

```po
fun add(left: int, right: int): int {
    return left + right;
}

fun add(left: int, right: num): num {
    return left +: right;
}
```

### Types and OOP

User-defined types support public and private members, constructors and methods. Instances copy by value.

```po
type Point {
    + x: int;
    - y: int = 7;

    + fun constructor(px: int): Point {
        this.x = px;
    }

    + fun sum(other: Point): int {
        return this.x + other.x;
    }

    + fun describe(): str {
        return "Point(" + (this.x as str) + ", " + (this.y as str) + ")";
    }
}

first := [5] as Point;        ## constructor call
second: Point = 9;            ## constructor call

print(first.x);
print(" ");
print(first.sum(second));
print("\n");

print(first.describe());
print("\n");

## y is private and reachable through a method
print(second.describe());
print("\n");

## Instances copy by value
copy := first;
copy.x = 100;
print(first.x);
print(" ");
print(copy.x);
print("\n");
```

### Modules

Modules use namespaces, aliases and wildcard imports. Exports are declared with `export`.

```po
use "./lib/greeting.po" as greeting;
use "./lib/greeting.po" as *;

print(greeting.hello("powang"));
print("\n");

## Wildcard import exposes the exported names directly
print(hello("wildcard"));
print("\n");
```

Standard library modules are imported by name.

```po
use strings;
use json;
use url;
use crypto;
```

### Collections

Arrays, maps and strings. Trailing commas are allowed in arrays, maps, calls and parameters.

```po
numbers := [1, 2, 3,];
pairs := ["name" >> "powang", "kind" >> "language",];

numbers: arr[int] = [10 20 30];
print(numbers[1]);
print("\n");

pairs = pairs + ["year" >> 2025];
print(pairs["name"]);
print(" ");
print(size(pairs));
print("\n");
```

Array arithmetic:

```po
print([1 2] + [3 4]);            ## 1, 2, 3, 4
print([1 2 3 4] - 2);            ## 1, 2
print(2 / [1 2 3 4]);            ## [[1, 2], [3, 4]]
```

Maps use `key >> value` pairs. Destructuring works for arrays and objects.

```po
[a, b] := pair;
[a: int, b] := pair;
[a, b]: int = pair;
[r:&, s] := pair;                ## r references pair[0]
```

For-each supports destructuring directly.

```po
for [key, value] >> pairs { println($"{key}={value}"); }
for [key: str, value: int] >> pairs { println($"{key}:{value}"); }
```

### Errors

Error-union return types use `T?`. The postfix `?` propagates errors. `fail` constructs an error value.

```po
fun validate(value: int): int? {
    if value < 0 {
        return fail("VALUE", "negative input", "value=" + (value as str));
    }
    return value;
}

fun double(value: int): int? {
    checked := validate(value)?;
    return checked * 2;
}

print(double(5));
print("\n");

rejected := double(-5);
print(typeof(rejected));
print(" ");
print(rejected.kind);
print(" ");
print(rejected.message);
print("\n");
```

try, catch and finally handle raised errors. Native error values expose kind, message, details, where, line, column, frames and cause.

```po
try {
    error("boom", "first detail", "second detail");
} catch problem {
    print(problem.kind);
    print(" ");
    print(problem.message);
    print(" ");
    print(size(problem.details));
    print("\n");
}

try {
    "abc" / 0;
} catch problem {
    print(problem.kind);
    print(": ");
    print(problem.message);
    print("\n");
}
```

### Tasks

Spawn a function call on a worker thread and wait for the result.

```po
fun sum_squares(limit: int): int {
    total: int = 0;
    for index := 0; index < limit; index += 1 {
        total += index * index;
    }
    return total;
}

fun run() {
    first := spawn sum_squares(100);
    second := spawn sum_squares(200);

    print(typeof(first));
    print(" ");

    print(wait(first));
    print(" ");
    print(wait(second));
    print("\n");
}

run();
```

### References

A parameter declared `&type` receives a reference to a variable, and the caller passes `&variable`. Reads and writes inside the function reach the caller's variable.

```po
fun increment(value: &int) {
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
- Arguments are still evaluated in the caller, and the parameter's operations use the normal type checks.

### Enums

A finite set of named constant values.

```po
type Color enum {
    RED,
    GREEN,
    BLUE,
}

c: Color = Color.RED;
print(c);              ## <Color: RED>
print(c == Color.RED); ## true
print(c :: Color);     ## true
```

Each variant is an instance of the enum type. Variants compare by name and type. Enums work with functions, typed declarations and `::` type checks. Match works on enums.

```po
fun describe(color: Color): str {
    return color match {
        case Color.RED >> "red"
        case Color.GREEN >> "green"
        case >> "blue"
    }
}
```

### Match

Pattern matching with literals, identifier bindings, typed bindings, wildcards and guards.

```po
match value {
    case 0 >> print("zero");
    case n if n < 0 >> print("negative");
    case _ >> print("positive");
}
```

### Pipelines

Pipelines pass the left value as the first argument.

```po
result := "  powang  " :> strings.trim :> strings.upper;
```

The pipeline operator is `:>`.

### Null safety

`?.` short-circuits on `nova`. `??` supplies a fallback.

```po
name := user?.name ?? "anonymous";
```

A declaration in an `if` condition is scoped to the block and uses `nova` as falsey.

```po
if name := user?.name {
    println($"Hello, {name}!");
}
```

### Constants

`const` creates a compile-time macro that is substituted everywhere it appears.

```po
const MAX_SIZE: int = 1024;
const DOUBLE_MAX = MAX_SIZE * 2;
```

`!` marks a runtime immutable value. It still occupies memory and can be passed around.

```po
buffer_size: int! = 64;
```

Constants cannot be reassigned and cannot be referenced.

### Comments

Line comments use `##`. Block comments use `#! ... !#`.

```po
## line comment

#!
This comment can span
more than one line.
!#
```

### Strings

Strings support interpolation with `$"..."`.

```po
name := "Ada";
println($"Hello, {name}! 2 + 2 = {2 + 2}");
```

Use `{{` and `}}` for literal braces inside an interpolated string.

Output and input builtins:

- `print(...)` writes each argument without adding a newline and returns the argument count.
- `println(...)` writes each argument and then a newline.
- `format(template, ...)` returns a formatted string with `{0}`, `{1}` and `{n/separator}` placeholders.
- `printf(template, ...)` formats and prints in one call.
- `input(receptor)` reads one line into `receptor`.
- `inputf(receptor, prompt)` prints `prompt` and then reads one line into `receptor`.

## Standard library

Import with `use name;`. Standard library modules live under `modules/`.

| Module | Purpose |
|---|---|
| `strings` | trim, upper, lower, replace, contains, starts_with, ends_with, slice, split, join, repeat, pad_left, pad_right, char_code, from_char_code, parse_int, parse_number, format_number |
| `math` | sqrt, log, cos, sin, tan |
| `json` | parse, stringify |
| `url` | encode, decode, parse_query, query_build |
| `crypto` | sha256, hmac_sha256, random_token, constant_time_compare |
| `time` | epoch, now_iso, format_epoch, sleep_ms |
| `env` | get, get_or, has |
| `args` | all, count, at |
| `log` | debug, info, warn, err, with_fields, set_level, is_enabled, access |
| `http` | get, post, request, serve, listen, stop |
| `http_router` | new, add, dispatch, middleware |

## CLI and REPL

```sh
powang                  # Runs the REPL
powang (--help | -h)    # Display usage
powang input.po         # Interprets an input file
```

Flags:

- `--ast output.json` dumps the AST to a JSON file.
- `--check` parses and type-checks only, does not execute.
- `--no-check` skips static type checking before execution.
- `--debug` prints a full traceback for internal errors.
- `--allow-system` allows `system()` while an HTTP server is running.

Everything after the input file belongs to the script and is exposed through the `args` module. Exit codes: 0 success, 1 language error, 2 usage, 3 internal, 130 interrupt. Recursion is guarded at 900 evaluation levels.

The REPL owns one state for the whole session, so variables declared on one line stay visible on the next. Type `exit` or press Ctrl-D to quit.

## Project layout

```
powang/
  powang.py            # interpreter entry point
  src/                 # lexer, parser, runtime, type checker, builtins, stdlib
  modules/             # standard library .po modules
  examples/            # example programs
  tests/               # test suite
  assets/              # banner and assets
  LICENSE
  pyproject.toml
  README.md
```

## License

MIT License. Copyright (c) 2025 POLA-LCS or Zara Atenea Pilling. See [LICENSE](LICENSE).
