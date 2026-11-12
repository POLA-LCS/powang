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

## Execution engines

Powang ships two stable execution engines.

- `vm` is the stack based bytecode virtual machine in `src/vm`. It is the default engine.
- `tree` is the tree-walking interpreter. It is the reference engine and the fallback.

Select an engine per run:

```sh
python powang.py --engine=vm main.po
python powang.py --engine=tree main.po
```

Select a default engine for a shell session:

```sh
POWANG_ENGINE=tree python powang.py main.po
POWANG_ENGINE=vm python powang.py main.po
```

A project can select an engine in `project.po`:

```po
module project;

export project: Project = Project.[
    engine >> "vm"
];
```

Inspect, trace or compare a program:

```sh
python powang.py vm disasm main.po
python powang.py vm run --trace main.po
python powang.py vm diff main.po
python powang.py vm bench --runs 3
```

The VM is the default. The tree walker remains the reference oracle and the
fallback. Both engines must produce the same output, the same runtime error
text, the same source positions and the same exit code.

## Native C++17 runtime (N3 core)

An optional native C++17 runtime lives under `native/`. It is not the default engine. The Python VM remains the default engine and the differential oracle, and the tree walker remains the reference engine and the fallback.

The native runtime consumes the same `PWB1` program image as the Python compiler. N3 core covers scalars, big integers with int64 promotion, globals, functions, recursion, closures by value and reference, defaults, named arguments, variadics, overload selection, range loops, iterators, UTF-32 strings, arrays, tuples, insertion ordered maps and sets, indexing, slicing, string and array operators, deep copy, interpolation, the format and character builtins, the container native methods, user types, constructors, public and private fields, instance methods, statics, enums, traits, default methods and operator overloading. Mixed int/num arithmetic and comparisons follow the Python VM cast order. Division and modulo by zero return nova for int and num. Float modulo follows the divisor sign, including signed zero. Native method lock enforcement, exact access-control, ambiguity and lock error text, modules, project values, externs, errors, references, tasks, file and task methods and the full host bridge remain. Runtime error stream and text parity is not complete, so the native runtime does not yet have full language parity.

The Python side of the build is under `src/vm/native/`. `source_gen.py` renders the generated `temp.cpp` translation unit into an in-memory buffer, and the default integrated compiler writes a temporary `temp.cpp` file for diagnostics. `compiler.py` runs the integrated `g++` driver, `build.py` configures and builds the runtime with CMake and Ninja, and `loader.py` compiles and runs an image. The generated source is temporary and is never committed.

Build the runtime with g++ 16.1.0 or a compatible C++17 compiler, CMake and Ninja:

```sh
cmake -S native -B build/native -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=g++
cmake --build build/native
```

The verified environment is Windows 11 with g++ 16.1.0, CMake 4.4.2 and Ninja 1.13.2.

Inspect, run and compile a program:

```sh
python powang.py vm native info
python powang.py vm native run main.po
python powang.py vm native compile --output build/main.exe main.po
```

`compile` accepts `--keep-source` to write `<output-stem>.cpp` next to the executable for debugging, for example `build/main.cpp` for `build/main.exe`. The package version is still `0.22.0` and N0, N1, N2 and the N3 core are milestones, not releases. Full native parity is not claimed.

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

powang is gradually typed. Annotated declarations, assignments, operators, calls and returns are checked. Unannotated code stays dynamic and degrades to `any`.

Built-in annotation types: `int`, `num`, `str`, `char`, `bool`, `arr`, `map`, `set`, `tup`, `any`, `nova`, `obj`, `task`, `file`, `handle`, `error`. Reference parameters use `&T`.

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

`obj` is the top type for user-defined type instances. `task`, `file`, `handle` and `error` annotate their runtime values. Member access on `obj` requires a cast.

```po
user_value: obj = Point.[1];
task_handle: task = spawn work();
file_handle: file = file.open("data.txt", "read");
error_value: error = fail("KIND", "boom");
```

Typed arrays accept an element type. A bare `arr` is sugar for `arr[any]`.

```po
numbers: arr[int] = [10 20 30];
mixed: arr = [1 "two" true];         ## arr[any]
typed_names: arr[str] = ["ada" "grace"];
```

Element types are checked on declarations, function arguments, return values, indexing and casts. Typed annotations also work in casts, for example `values as arr[int]`. The runtime representation is still one `arr` type, so typed arrays add no runtime cost.

Union annotations accept a value from any branch. Qualifiers apply to the whole annotation.

```po
score: int | num = 2;
score = 2.5;                    ## accepted
name: int | str = "Ada";        ## accepted
mixed: arr[int | num] = [1, 2.5];
bad: int | str = 3.14;          ## rejected
```

`typeof` stays shallow. It reports `arr`, `tup` or the user type name. `typedeep` reports the structural type, including element and position types.

```po
print(typeof(tup.[2, 3.14]));   ## tup
print(typedeep(tup.[2, 3.14])); ## tup[int, num]
print(typedeep([1, 2.5]));      ## arr[int | num]
```

### Construction

`Type.[args]` is the canonical instantiation form. Native values use the same dot-bracket form.

```po
integer_value := int.[42];
number_value := num.[2];
string_value := str.[25];
boolean_value := bool.[0];

numbers := arr.[2, 3, 4];             ## arr[int]
mixed := arr[int | num].[2, 3.14];    ## typed construction
pair := tup.[2, 3.14, ""];            ## tup[int, num, str]
typed_pair := tup[int, str].[2, "hi"];
settings := map.["debug" >> true];    ## map construction
```

Array, map and tuple literals are parser sugar for the same construction. `[1, 2, 3]` builds `arr[int].[1, 2, 3]`, `["a" >> 2]` builds `map.["a" >> 2]`, and `.[1, 2]` builds a tuple. Mixed arrays infer a union, never `any`.

Empty literals:

```po
[]      ## arr[any]
.[]     ## tup
[>>]    ## map[any, any]
[/]     ## set[any]
[/1, 2, 3]  ## set[int].[1, 2, 3]
```

`[>>]` is only the empty map literal. Non-empty maps use `["key" >> value]`. `[>> "a" >> 1]` is invalid.

### Native methods

Native type names are namespaces. Each method has a value form and, where mutation makes sense, a reference form.

```po
values := [1, 2];
copy := values :> arr.push(3);     ## values unchanged
values &> arr.push(3);             ## values becomes [1, 2, 3]

values &> arr.add([4, 5]);         ## values becomes [1, 2, 3, 4, 5]
```

`push` adds one value. `add` flattens a container into the receiver. The value form returns a new value. The reference form mutates the caller and returns `&source`.

```po
arr.push(source, value) -> arr
arr.push(&source, value) -> &arr
arr.pop(&source, index = -1) -> &arr
arr.popget(&source, index = -1) -> element
arr.put(&source, index, value) -> &arr
arr.popval(&source, value, max = -1) -> &arr
```

The same pattern exists for `str`, `map`, `tup` and `set`:

```po
text &> str.add("!");
settings := [>>];
settings["debug"] = true;          ## inserts or replaces
map.has(settings, "debug");
map.pop(&settings, "debug");
map.popget(&settings, "debug");

unique := [/1, 2, 2, 3];
set.has(unique, 2);
set.union(unique, [/3, 4]);
```

`&>` is sugar for a reference pipeline. `x &> f(y)` is `&x :> f(y)`. The target may be a variable, a property such as `this.x`, or an array element such as `values[0]`. Parentheses are optional for pipeline targets, so a function with one required parameter and default parameters can be called as `value :> strings.split`.

The `char` type also has native methods. `code()` returns the Unicode code point, `to_str()` returns a one-character string, and the ASCII predicates are available as methods.

```po
letter := 'A';
print(letter.code());      ## 65
print(letter.to_str());    ## A
print(letter.is_alpha());  ## true
```

### Copy semantics and locks

Plain parameters receive a deep copy. Mutation inside the function changes only the copy. `&` parameters receive a reference and mutate the caller.

```po
fun local_edit(values: arr[int]) {
    values[0] = 9;                 ## caller unchanged
}

fun caller_edit(values: &arr[int]) {
    values[0] = 9;                 ## caller changed, call with &values
}
```

Container qualifiers are independent locks. Outer `!` locks structure. Inner `!` locks elements or values.

```po
arr[int]       ## mutable structure, mutable elements
arr[int]!      ## locked structure, mutable elements
arr[int!]      ## mutable structure, locked elements
arr[int]!!     ## both locked, same as arr[int!]!

map[str, int]!       ## no insert, pop or merge, values mutable
map[str, int!]       ## insert and pop allowed, values immutable
map[str, int]!!      ## both locked
```

Tuple types are immutable by default. Any `!` on a tuple or directly on a tuple element is rejected.

### Generic user types

```po
type Box[+][T] {
    | value: T;
}

box := Box[int].[5];
```

Both `type Box[T][+]` and `type Box[+][T]` are accepted. Type parameters flow through constructor members, properties, method parameters and method returns.

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

`loop` repeats a block. `loop if` checks the condition before each iteration and accepts the same declarations as `if`.

```po
loop {
    if done {
        break;
    }
}

loop if index < 10 {
    index += 1;
}

loop if line := input("") {
    if line == "quit" {
        break;
    }
    print(line);
}
```

Loops can be labeled. `break` and `continue` accept the label to target an outer loop.

```po
for |rows| row >> matrix {
    for cell >> row {
        if cell == target {
            break rows;
        }
    }
}
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

### Function types and lambdas

A function type is `fun[arg_types..., ret_type]`. The last type is the return. The bare name `function` is not a type annotation.

```po
handler: fun[int, int];
apply: fun[fun[int, int], int, int];
```

Lambdas use `fun` in expression position. They support block and `>>` bodies.

```po
double := fun(value: int): int >> value * 2;
add := fun(left: int, right: int): int {
    return left + right;
};
```

A named lambda can recurse:

```po
factorial := fun fact(value: int): int {
    if value <= 1 { return 1; }
    return fact(value - 1) * value;
};
```

Capture is by value by default. Add `&` to capture by reference.

```po
base := 10;
add_base := fun(value: int): int >> value + base;

counter := 0;
bump := fun &(value: int) { counter += value; };
```

Functions are values. They can be passed, returned and stored in arrays.

```po
fun apply(function: fun[int, int], value: int): int {
    return function(value);
}

print(apply(double, 7));
print(typedeep(double));  ## fun[int, int]
```

### Variadics and spread

A variadic parameter collects the remaining arguments into an array.

```po
fun sum(values: int...): int {
    total := 0;
    for value >> values {
        total += value;
    }
    return total;
}

sum();
sum(1, 2, 3);
```

Generic variadic functions infer the element type. Explicit type arguments force the template overload.

```po
fun first[T](values: T...): T {
    return values[0];
}

first(7, 8, 9);
first[str](..."ab");

fun add(a: int, b: int): int >> a + b;
fun add[T](a: T, b: T): T >> a + b;

add(1, 2);       ## concrete
add[int](1, 2);  ## template
```

Spread uses a prefix `...` and only works in argument position. Arrays, tuples, sets, maps and strings can be spread.

```po
sum(...values);
sum(...[1, 2, 3]);
sum(...pairs);
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

    + fun this.sum(other: Point): int {
        return this.x + other.x;
    }

    + fun this.describe(): str {
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

Access defaults remove repeated specifiers. `type T[+]` makes every member public by default, and `type T[-]` makes every member private by default. A plain `type T` still requires an explicit `+` or `-` on every member. Repeating the default is allowed but produces a warning.

Instance methods must declare their receiver with `this.` or the shorter `.` marker. A method without the marker is static and is called from the type name.

```po
type Point[+] {
    | x: int;

    fun origin(): Point {          ## static
        return Point.[0];
    }

    fun this.get(): int {          ## instance
        return this.x;
    }

    fun .plus(value: int): int {   ## same as this.plus
        return this.x + value;
    }
}

origin := Point.origin();
origin.get();
origin.plus(2);
```

```po
type Person[+] {
    id: int!;          ## public write-once member, not a parameter
    | name: str;       ## public constructor parameter
    | address: str;    ## public constructor parameter
    age: num;          ## public member, not a parameter
    - cache: int;      ## private member
}
```

`|` marks constructor members. The compiler generates a public constructor whose parameters follow declaration order. The generated body assigns every parameter to `this` and returns `this`.

```po
first := Person.["Ada", "London"];
second := Person.[name >> "Ada", address >> "London"];
third := .["Ada", "London"] as Person;   ## legacy form, still valid
```

Named and positional arguments cannot be mixed. Duplicate names, unknown names and missing required names are errors.

A zero-parameter explicit constructor becomes a body hook. The generated assignments run first, then the author body, then `this` is returned.

```po
type Account[+] {
    | owner: str;

    fun constructor {
        if owner == "" {
            error("owner is required");
        }
    }
}
```

If an explicit constructor declares parameters, it replaces generation. Constructor members are then ignored and produce a warning. A `|` member declared `name: type!` is allowed and performs its single write from the constructor. The `const` keyword cannot be combined with `|`.

### Traits

Traits describe a structural contract. A type satisfies a trait by declaring the required properties and methods. There is no `impl` block.

```po
trait Drawable {
    | name: str;
    fun draw(): str;
    fun describe(): str {
        return $"name={this.name} draw={this.draw()}";
    }
}

type Screen[+] {
    | name: str;
    fun this.draw(): str {
        return "screen";
    }
}

value: Drawable = Screen.["main"];
value.draw();
value.describe();
```

A method signature ending with `;` is required. A method with a body is a default. Default bodies use only the declared trait contract. Accessing an undeclared member is a checker error.

Generic constraints use `T: Trait` or `T: TraitA & TraitB`.

```po
fun render[T: Drawable](value: T): str >> value.describe();
```

When two traits require the same method name with incompatible signatures, define trait-qualified methods inside the type and use qualified calls.

```po
type Dual[+] {
    fun Drawable.draw(): str >> "drawable";
    fun Named.draw(): int >> 42;
}

Drawable.draw(dual);
Named.draw(dual);
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

Bare names import built-in language modules from the Powang `modules/` directory. They do not search the input directory by default.

```po
use strings;
use json;
use url;
use crypto;
```

Relative modules use leading dots. One dot searches the input directory, two dots search its parent, and each additional dot goes up one more directory.

```po
use .helper;       ## <input-directory>/helper.po or helper/
use ..shared;      ## <input-directory>/../shared.po or shared/
use ...common;     ## <input-directory>/../../common.po or common/
```

Explicit path imports remain available and are unaffected.

```po
use "./lib/greeting.po" as greeting;
```

### Cross-module type checking

Imported modules are parsed and checked before the importing file. Aliased and wildcard imports carry functions, variables, object types and traits across module boundaries.

```po
## lib/geometry.po
module geometry;

export type Point[+] {
    | x: int;
    | y: int;
}

export fun distance(a: Point, b: Point): int {
    dx: int = a.x - b.x;
    dy: int = a.y - b.y;
    return dx * dx + dy * dy;
}
```

```po
## main.po
use "./lib/geometry.po" as g;

a: g.Point = g.Point.[0, 0];
b: g.Point = g.Point.[3, 4];
print(g.distance(a, b));
```

Wildcard imports expose exported names directly.

```po
use "./lib/geometry.po" as *;

p: Point = Point.[2, 3];
print(distance(p, Point.[0, 0]));
```

Wrong arguments, missing members and arity errors are reported in the importing file. Errors inside an imported module are reported at the import statement. Cyclic imports are detected without running the module.

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

Slicing uses `from >> to`. Both sides are optional. Negative indices count from the end and bounds are clamped.

```po
text := "abcdef";
print(text[>>]);      ## abcdef
print(text[2 >>]);    ## cdef
print(text[>> 3]);    ## abc
print(text[-3 >>]);   ## def
print(text[>> -1]);   ## abcde
print(text[-1]);      ## f
```

The same syntax works for arrays and tuples.

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

try, catch and finally handle raised errors. Native error values expose kind, message, details, where, line, column, frames and cause. `frames` records the call stack, innermost first, formatted as `at function (file:line:column)`.

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

Spawn a function call on a worker thread and wait for the result. Method and static method calls are also supported, for example `spawn worker.run()` and `spawn Math.double(4)`.

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

Destructuring patterns cover arrays, tuples and objects. Rest bindings collect the remaining elements. Range patterns use an inclusive lower bound and an exclusive upper bound.

```po
match values {
    case [head, ...tail] >> ...
    case .[a, b] >> ...
    case Point.[x, y] >> ...
    case 0 >> 10 >> ...
    case _ >> ...
}
```

A match on `bool` or an enum warns when a value or variant is missing. Unreachable cases also produce warnings. Add a wildcard or cover every value to silence the exhaustiveness warning.

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

### Characters

A `char` is one Unicode scalar value, not a byte. Character literals use single quotes.

```po
letter: char = 'A';
newline := '\n';
emoji := '\u{1F600}';
```

Escapes include `\n`, `\t`, `\r`, `\\`, `\'`, `\"`, `\0` and `\u{HEX}`. A literal must contain exactly one scalar value. Surrogate code points and values above `U+10FFFF` are rejected. Unicode escapes also work inside strings.

String indexing and string iteration return `char`. Slicing still returns `str`, so a slice can produce a string while an index produces one character.

```po
text := "aé😀";
print(text[1]);   ## é, as a char
print(text[-1]);  ## 😀, as a char

for character >> text {
    print(character);
}
```

`str.get(index)` also returns a `char`. `str.chars()` materializes the whole string as `arr[char]` when an array is more convenient.

```po
letters := text.chars();
```

Characters concatenate with strings through `+`. Two characters also concatenate into a string. Comparisons use code point order.

```po
print("x" + 'y');  ## xy
print('a' + "b");  ## ab
print('a' + 'b');  ## ab
print('a' < 'b');  ## true
```

Explicit casts convert between `char` and `str`. A string must contain exactly one scalar value when cast to `char`.

```po
text := 'x' as str;
letter := "y" as char;
constructed := char.["z"];
```

Character builtins accept a `char` or a one-character `str`:

- `is_digit`, `is_alpha`, `is_alnum`, `is_space`, `is_upper`, `is_lower` and `is_ascii` return `bool`.
- `ord(value)` returns the Unicode code point.
- `chr(code)` returns the character for a Unicode scalar value.
- `digit_value(value)` returns `0` to `9`, or `-1` for a non-digit.

```po
print(ord('A'));          ## 65
print(chr(65));           ## A
print(is_digit('7'));     ## true
print(digit_value('7'));  ## 7
```

The native methods `code`, `to_str`, `is_digit`, `is_alpha`, `is_alnum`, `is_space`, `is_upper`, `is_lower` and `is_ascii` are also available on `char` values.

## Standard library

Bare `use name;` resolves a built-in module under `modules/`. Use leading dots for relative files or directories, or a quoted path for an explicit path.

| Module | Purpose |
|---|---|
| `strings` | trim, upper, lower, replace, contains, starts_with, ends_with, slice, split, join, repeat, pad_left, pad_right, char_code, from_char_code, parse_int, parse_number, format_number. The character builtins `ord` and `chr` are preferred in new code. |
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
- `--no-warnings` suppresses non-fatal warnings on stderr.
- `--debug` prints a full traceback for internal errors.
- `--allow-system` allows `system()` while an HTTP server is running.

Everything after the input file belongs to the script and is exposed through the `args` module. Exit codes: 0 success, 1 language error, 2 usage, 3 internal, 130 interrupt. Recursion is guarded at 900 evaluation levels.

The REPL owns one state for the whole session, so variables declared on one line stay visible on the next. Type `exit` or press Ctrl-D to quit.

## Project configuration

A project can place a `project.po` file in its root. `powang run` requires it. Running a file directly or using the REPL also loads it when present. The file must start with `module project;` and export a `project: Project` value.

```po
module project;

export project: Project = Project.[
    modules >> ["pygame_host"],
    paths >> ["."],
    logLevel >> "info",
    allowSystem >> false,
];
```

`Project` is a built-in object type. Its fields are:

| Field | Type | Meaning |
|---|---|---|
| `modules` | `arr[str]` | allowed extern modules |
| `paths` | `arr[str]` | additional module search paths |
| `logLevel` | `str` | log level |
| `allowSystem` | `bool` | allow system access |

Member access is checked and works at runtime:

```po
print(project.logLevel);
print(project.modules[0]);
```

When `project.po` is loaded, the `project` value is also available implicitly inside imported modules. The `Project` type is registered as a runtime built-in object type. It cannot be redeclared.

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
