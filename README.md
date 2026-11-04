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
| [`examples/references.po`](examples/references.po) | reference parameters that mutate the caller |

## Editor support

The repository ships a complete Visual Studio Code extension under `editors/vscode/`
that provides **both** syntax highlighting and LSP diagnostics/completion. No
third-party extensions are needed.

### Install the extension

1. Copy the `editors/vscode` folder to your VS Code extensions directory:
   - Windows: `%USERPROFILE%\.vscode\extensions\powang-0.2.0\`
   - macOS: `~/.vscode/extensions/powang-0.2.0/`
   - Linux: `~/.vscode/extensions/powang-0.2.0/`
2. Reload VS Code (`Ctrl+Shift+P`, then `Developer: Reload Window`).
3. Open any `.po` file. You get highlighting, diagnostics and completion automatically.

Alternatively, run VS Code from the command line with the extension in development
mode:

```bash
code --extensionDevelopmentPath=editors/vscode
```

This opens a new VS Code window with the extension loaded. Any `.po` file opened in
that window gets highlighting and diagnostics.

### What the extension provides

- **Syntax highlighting** via the TextMate grammar in `syntax/powang.tmLanguage.json`.
- **Diagnostics** from the parser and the gradual type checker, published as you type.
- **Keyword and builtin completion** with 30 items.
- **Language configuration**: brackets, comments, indentation rules, auto-closing pairs.

### What the LSP does

- Publishes syntax diagnostics from the parser.
- Publishes type diagnostics from the gradual checker.
- Offers keyword and builtin completion.

It does not yet provide hover, rename or goto-definition.

### Vim

Copy `syntax/powang.vim` into `~/.vim/syntax/` (or `~/vimfiles/syntax/` on
Windows) and add:

```vim
autocmd BufRead,BufNewFile *.po set filetype=powang
```

Sublime Text, GitHub Linguist and any TextMate consumer can use
`syntax/powang.tmLanguage.json` directly.

## References

A parameter declared `&type` receives a reference to a variable, and the caller passes
`&variable`. Reads and writes inside the function reach the caller's variable:

```po
fun increment(value: &integer) {
    value += 1;
}

x := 10;
increment(&x);
output(x);        ## 11
```

Rules:

- References are explicit at the call site: `increment(&x)`, not `increment(x)`.
- Only variables can be referenced. Constants are rejected.
- A reference lives for one call. It cannot be stored, returned, or sent to a task.
- Arguments are still evaluated in the caller, and the parameter's operations use the
  normal type checks.

## Get started
You need [Python3](https://www.python.org/) 3.12 or newer.

- Clone the repository with:
```git clone https://github.com/POLA-LCS/powang```

- Go to `./powang`
- Run `python powang.py --help`
- Create the file `main.po`
- Write your first hello world with `output("Hello, world!\n");`
- Run it with `python powang.py main.po`
