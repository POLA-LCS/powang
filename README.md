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
- [X] References: `fun f(x: &integer)` with `f(&variable)`.
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

Syntax highlighting and diagnostics are provided without any third-party runtime
dependency.

- `syntax/powang.tmLanguage.json`: TextMate grammar usable in Visual Studio Code,
  Sublime Text, GitHub Linguist and any editor that reads TextMate grammars.
- `syntax/powang.vim`: Vim syntax file.
- `tools/powang_lsp.py`: a minimal Language Server Protocol server. It publishes
  diagnostics from the parser and the gradual type checker, and offers keyword and
  builtin completion. It runs over standard input and output, so any LSP client can
  use it with the command `python tools/powang_lsp.py` from the repository root.

The repository ships a ready-to-install Visual Studio Code extension under
`editors/vscode/`. It contributes the `powang` language, the grammar and the
language configuration (brackets, comments, indentation). To use it:

1. Open VS Code.
2. Press `Ctrl+Shift+P`, run `Developer: Install Extension from Location...`, and
   select the `editors/vscode` folder.
3. Reload the window. Every `.po` file now opens with highlighting.

The workspace `.vscode/settings.json` already maps `*.po` to `powang` and points at
the grammar and the LSP server. It also recommends the **TextMate Languages** and
**LSP Client** extensions, which VS Code prompts you to install on first open.

For diagnostics and completion, install the **LSP Client** extension and let the
workspace settings start `python tools/powang_lsp.py` from the repository root. The
server publishes parser and type-checker diagnostics and keyword and builtin
completion.

For Vim, copy `syntax/powang.vim` into `~/.vim/syntax/` (or `~/vimfiles/syntax/`
on Windows) and add:

```vim
autocmd BufRead,BufNewFile *.po set filetype=powang
```

The server is intentionally small. It reports diagnostics and completions only; hover,
rename and goto-definition are left for a future release.

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