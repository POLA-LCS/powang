# Powang programming language

![powang banner](./powang_banner.jpeg)

Hiii, this is POLA, a software engineering student, and this is my own programming language.  
It is based on the lisp-type operations but with higher level interation.

> [!WARNING]
> It's still work in progress so expect to encounter bugs or undefined behaviours.

## TODO
- [X] Comments `##`.
- [X] `number`.
- [X] `string`.
- [X] `list`.
- [X] `expression`.
- [X] Standard console output `stdout`.
- [X] Fancy print with `print` (almost 1:1 with python print).
- [ ] User types.
- - [ ] Methods.
- - [ ] Inheritance.
- [ ] Functions.
- - [ ] Signature.
- - [ ] Define.
- - [ ] Profiles (like C++ templates).
- [ ] A better lexical analysis.
- [ ] References.
- [ ] Logical operators.
- [X] Arithmetics (see [Arithmetic Operators](docs/Arithmetics.md)).
- [ ] User error handling.
- [X] Decide when to preprocess the tokens into values and when into raw tokens.
- [X] Control flow:
- - [X] if.
- - [X] else.
- - [X] else if.
- - [ ] for.
- - [ ] each.

## Get started
You need [Python3](https://www.python.org/).

- Clone the repository with:  
```git clone https://github.com/POLA-LCS/powang```

- Go to `./powang`  
- Run `powang.py --help`  
- Create the file `main.po`   
- Write your first hello world with `stdout 'Hello,\a32world!\n'`  
- Run it with `powang.py main.po`  