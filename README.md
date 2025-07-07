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
- [ ] Error handling.
- [X] Control flow:
- - [X] if.
- - [X] else.
- - [X] while.
- - [X] for.
- - [X] each.
- - [X] else if.

## Get started
You need [Python3](https://www.python.org/).

- Clone the repository with:  
```git clone https://github.com/POLA-LCS/powang```

- Go to `./powang`  
- Run `powang.py --help`  
- Create the file `main.po`   
- Write your first hello world with `output("Hello, world!\n");`  
- Run it with `powang.py main.po`  