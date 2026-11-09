# LSP changes

The current fix format is presented as:
- Context
- Example
- Misbehaviour
- Intended behaviour
- Extra

All of that separated by ';'

## async-await

**Variable declaration (walrus) from await call**;
`x := await async_func()`;
Variable's type is being displayed as `any`;
Show the return type of the `async_func`;
Propose another alternative.

**Variable declaration (walrus) from explicit type instance**;
`x := int.[69]`, `x := Coord.[3.14, 1.56]`;
LSP is creating redundant information by placing the type as if it's weren't there: `x: int := int.[69]`, `x: Coord := Coord.[3.14, 1.56]`;
Remove the redundant information, keep it clean with `x := int.[69]`

**Variable declaration (walrus) from spawn task**;
`x := spawn task_int()`;
Variable's type is being displayed as `any`
Show the type `task` with template of the return type of the `task_int`: `x: task[int] := spawn task_int()`

**For loop**;
`for x >> array`, `for x >> array if x > 0`, `for i >> 0 >> 10`;
LSP does not display the inferred type of the bare identifier `x`;
Add the inferred type in a `for x: type ...` way so `for x >> array` for an `arr[int]` makes `for x: int >> array` LSP adding just the ": int ".

**Destructuring**;
`[a, b] := pair`, `[a, b] := [1, 2]`;
LSP is not adding the proper types for each one, e.g: `[a, b] := [1, "hola"]` should generate `int` for `a` and `str` for `b` so the LSP display should be `[a: int, b: str] := [1, "hola"]`