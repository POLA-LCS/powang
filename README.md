# powang: The multi-purpose programming language written by me :D.

![powang banner](./assets/powang_banner.jpeg)

> [!WARNING]
> It's still work in progress so expect to encounter bugs or undefined behaviours.

Hiii, this is POLA, a software engineering student, and this is my own programming language.  
Initally based on the lisp operators but later changed into a more natural language.

## TODO
- [X] Comments `##`.
- [X] Primitive types: `nova`, `some`, `integer`, `number`, `string`, `array`, `map`.
- [X] Standard io `output(...)`, `input(var)`.
- [X] Type modifiers like constant "type!" and weak "@type".
- [X] User types.
- - [X] Methods.
- - [ ] Inheritance.
- [X] Functions.
- - [ ] Signature.
- - [X] Define.
- - [ ] Templates.
- [X] A better lexical analysis.
- [ ] References.
- [X] Logical operators.
- [X] Arithmetics (see [Arithmetic Operators](examples/arithmetics.po)).
- [X] Error handling: `try`/`catch`/`finally`, `fail`, error unions `T?` and `?`.
- [X] Static typing: gradual checker with `--check`.
- [X] Modules: namespaces, aliases, wildcard imports and `export`.
- [X] Standard library: `strings`, `json`, `url`, `env`, `args`, `time`, `crypto`, `http`, `http_router`, `log`.
- [X] Tasks: `spawn`, `wait`, `cancel`, `task_status`.
- [X] Control flow:
- - [X] if.
- - [X] else.
- - [ ] while.
- - [X] for.
- - [X] each.
- - [X] else if.

## Examples

| File | Shows |
|---|---|
| [`examples/variables.po`](examples/variables.po) | declarations, weak types, constants |
| [`examples/arithmetics.po`](examples/arithmetics.po) | operators, casting, arrays and strings |
| [`examples/functions.po`](examples/functions.po) | functions and overloads |
| [`examples/control-flow.po`](examples/control-flow.po) | if/else, loops, for-each, try/catch/finally |
| [`examples/errors.po`](examples/errors.po) | raising, catching, error unions and `?` |
| [`examples/types.po`](examples/types.po) | user types, constructors, methods, privacy |
| [`examples/collections.po`](examples/collections.po) | arrays, maps, strings, `%` and exponent literals |
| [`examples/modules.po`](examples/modules.po) | module namespaces, aliases and wildcard imports |
| [`examples/stdlib.po`](examples/stdlib.po) | strings, json, url and crypto |
| [`examples/tasks.po`](examples/tasks.po) | spawn and wait |

## Get started
You need [Python3](https://www.python.org/) 3.12 or newer.

- Clone the repository with:  
```git clone https://github.com/POLA-LCS/powang```

- Go to `./powang`  
- Run `python powang.py --help`  
- Create the file `main.po`   
- Write your first hello world with `output("Hello, world!\n");`  
- Run it with `python powang.py main.po`  