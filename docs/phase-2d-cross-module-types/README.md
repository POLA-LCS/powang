# Phase 2D: cross-module type checking

## 1. Scope

This phase checks imported and exported types across Powang module files.

In scope:

- Parse and type-check imported modules before checking the importer.
- Check aliased imports with `use "./lib.po" as lib;`.
- Check wildcard imports with `use "./lib.po" as *;`.
- Check imported functions, variables, object types and traits.
- Check module-qualified calls such as `lib.function(args)`.
- Check module-qualified type annotations such as `lib.Point`.
- Check module-qualified type construction such as `lib.Point.[x, y]`.
- Report call-site errors in the importing file.
- Report imported module errors at the import statement.
- Cache module checks and detect import cycles.
- Run qualified object types and traits at runtime.

Out of scope:

- Exporting `const` declarations. `const` remains a compile-time macro and is not a module value.
- Full generic substitution for imported generic object types.
- Two modules exporting the same runtime type name with distinct nominal identities.
- Async and await.
- Package registry.
- Formatter and linter.

## 2. Module type model

Add `_ModuleTypeInfo`:

```text
name
path
functions: name -> signatures
variables: name -> type
object_types: exported name -> type info
traits: exported name -> trait info
all_object_types: all checked module types
all_traits: all checked module traits
exports: name -> kind
errors: imported module diagnostics
legacy: no explicit exports
loading: cycle marker
```

The checker keeps a module cache keyed by resolved path. The cache is shared by parent and child checkers, so a module is checked once per run.

## 3. Resolution and checking

The checker resolves modules with the same rules as the runtime loader:

- `use name` searches `modules/name`.
- `use "./path.po"` resolves relative to the importing file.
- Directory modules read every `.po` file in the directory.

For each imported module:

1. Save the current parser type tables.
2. Use fresh type alias and user type tables for the module.
3. Parse every source file.
4. Check the combined AST with a child checker.
5. Collect exported names and their types.
6. Restore the importer type tables.
7. Cache the module information.

A module with no explicit exports uses the legacy behavior and exports all top-level names.

## 4. Aliased imports

```po
use "./lib/geometry.po" as g;
```

The alias becomes a module value. The checker exposes exported functions, variables, object types and traits through the alias.

- `g.add(1, 2)` checks against the exported signatures.
- `g.version` returns the exported variable type.
- `g.Point` is a valid type annotation.
- `g.Point.[x, y]` checks the module constructor.
- Imported signatures have their exported type and trait names qualified to the alias.

## 5. Wildcard imports

```po
use "./lib/geometry.po" as *;
```

Wildcard imports copy exported functions, variables, object types and traits into the importing scope.

- Collisions with existing names are checker errors.
- Imported types can be used unqualified.
- Imported traits work in annotations and generic constraints.

## 6. Diagnostics

Call-site errors are reported in the importing file:

```text
ln: 3 | [TYPE ERROR] (in function call: g.add) Types doesn't match:
      | expected int
      | but str was encounter
```

Missing members and arity errors are reported at the call site.

Imported module errors are reported at the import statement:

```text
ln: 1 | [TYPE ERROR] (in import) module 'bad' has type errors:
      | expected int but str was encounter
```

Cyclic imports are reported at the import statement.

## 7. Runtime support

Qualified type annotations and construction resolve through the module value:

```po
a: g.Point = g.Point.[0, 0];
```

Runtime `Project`, object types and traits keep their existing behavior. Qualified type values use the original nominal type name so a value can cross module function boundaries without an implicit conversion. The checker still tracks the qualified static type.

Qualified trait annotations are accepted and behave as checker contracts at runtime.

## 8. Limitations

- `const` declarations are not exported.
- Imported generic object types are checked structurally but full generic substitution is not implemented.
- Two modules exporting the same runtime type name share runtime nominal identity. The checker still distinguishes their qualified static types.

## 9. Tests

- Aliased and wildcard imports.
- Imported variables and object types.
- Imported traits and generic constraints.
- Qualified type annotations and construction.
- Directory modules.
- Legacy modules without exports.
- Wrong argument types at the call site.
- Missing members and arity errors.
- Missing modules.
- Imported module internal errors.
- Import cycles.
- Wildcard collisions.
- LSP cross-module diagnostics.

## 10. Acceptance criteria

- Imported function calls are checked in the importer.
- Imported object types and traits are checked in the importer.
- Qualified and wildcard imports work.
- Call-site errors point at the importing file.
- Imported module errors point at the import statement.
- Cycles are detected without crashing.
- Qualified object types and traits work at runtime.
- All existing tests pass in normal and `-O` modes.
- The LSP surfaces cross-module diagnostics.
