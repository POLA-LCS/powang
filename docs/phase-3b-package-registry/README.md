# Phase 3B: package registry and dependency resolver

## 1. Scope

This phase adds a package manifest, a lock file, a semver dependency resolver, a registry client, a local package cache and the `powang pkg` command family.

In scope:

- `powang.toml` package metadata and dependency declarations.
- `powang.lock` deterministic resolution output.
- Semver versions and caret, tilde, exact and comparison constraints.
- Registry and path dependencies.
- Transitive dependency resolution with backtracking.
- A single selected version per package name.
- Lock reuse and explicit update.
- Local directory registries and HTTP or HTTPS registries.
- SHA-256 archive integrity checks.
- Safe tar.gz extraction.
- A global package cache under `POWANG_HOME`.
- A project install directory under `.powang/packages`.
- Runtime and type checker module resolution for installed packages.
- `powang pkg init`, `add`, `remove`, `install`, `update`, `list`, `tree`, `search` and `clean`.
- LSP diagnostics for files that import packages.
- Tests for resolution, installation, CLI, runtime, checker and LSP diagnostics.

Out of scope:

- Git dependencies.
- Prerelease semver versions.
- Multiple simultaneous versions of the same package.
- Registry publishing, authentication and ownership.
- Dev, build and optional dependencies.
- Workspaces and monorepos.
- Platform-specific lock metadata.
- Package signing.

## 2. Manifest

Package metadata lives in `powang.toml` at the project root.

```toml
[package]
name = "app"
version = "0.1.0"
description = "Example application"

[dependencies]
mathlib = "^1.2.0"
utils = ">=1.0.0 <2.0.0"
local = { path = "../local" }

[registry]
url = "https://registry.example.com"
```

The existing `[extern]`, `[paths]` and `[host]` sections remain valid. The package manager preserves them when it rewrites the manifest.

Dependency values are either a version constraint string or a table with `path` or `version`. A path dependency may not also declare a version. A path dependency may not declare a registry.

Package names use lowercase letters, digits and underscores, and start with a letter.

The manifest hash covers only the registry URL and the dependency declarations. Changing the project version or description does not invalidate the lock.

## 3. Lock file

`powang.lock` is deterministic JSON.

```json
{
  "format": 1,
  "manifestHash": "...",
  "packages": {
    "mathlib": {
      "version": "1.2.0",
      "source": {
        "kind": "registry",
        "registry": "https://registry.example.com",
        "archive": "archives/mathlib-1.2.0.tar.gz",
        "sha256": "..."
      },
      "dependencies": {
        "utils": "^1.0.0"
      }
    }
  }
}
```

Path packages use:

```json
{
  "kind": "path",
  "path": "../local"
}
```

Registry source data is authoritative for installation. If the registry index is unavailable, an existing lock and cache can still reinstall a registry package.

`powang.lock` should be committed. `.powang/` should not be committed. The installer creates `.powang/.gitignore` with `*`.

## 4. Cache and install layout

The global cache lives under `POWANG_HOME`. The default is `~/.powang`.

```text
~/.powang/cache/
  registries/<sha256-of-url>/index.json
  archives/<sha256>.tar.gz
```

The project install tree lives under `.powang/packages`.

```text
.powang/packages/
  mathlib/1.2.0/
    powang.toml
    modules/
      mathlib.po
```

A package archive has its package root at the archive root. It must contain a `powang.toml` and a `modules` directory with at least one `.po` file. Packages may use `modules/<name>.po` or `modules/<name>/`.

Path dependencies are not copied. Their source directory is added directly to the module search path, so edits are visible without reinstalling.

## 5. Registry protocol

A registry serves `index.json` at its root.

```json
{
  "format": 1,
  "packages": {
    "mathlib": {
      "latest": "1.2.0",
      "description": "Math helpers",
      "versions": {
        "1.2.0": {
          "archive": "archives/mathlib-1.2.0.tar.gz",
          "sha256": "64 lowercase or uppercase hexadecimal characters",
          "dependencies": {
            "utils": "^1.0.0"
          }
        }
      }
    }
  }
}
```

An archive path is relative to the registry base URL or registry directory. It may also be an absolute HTTP, HTTPS or file URL.

A registry URL may be a local directory, an `index.json` file path, or an HTTP or HTTPS base URL. `POWANG_REGISTRY_URL` supplies a registry when the manifest does not.

The client verifies the SHA-256 hash before extracting an archive. It rejects absolute paths, `..` components, symbolic links, hard links and device entries in tar archives.

## 6. Resolver

The resolver selects one version for each package name.

- It starts from the root dependencies.
- It reads transitive dependencies from the registry index or from a path package manifest.
- It filters available versions through every accumulated constraint.
- It tries the highest matching version first.
- It backtracks when a selected version introduces a conflict.
- It prefers the locked version when the lock is current and the package is not being updated.
- It reports the requesters and their constraints when no version matches.
- It treats cycles as already selected nodes and does not recurse forever.

Supported constraints:

- `1.2.3` exact.
- `^1.2.3` compatible with the major version.
- `^0.2.3` compatible with the minor version.
- `^0.0.3` compatible with the patch version.
- `~1.2.3` compatible with the minor version.
- `~1` compatible with the major version.
- `>=1.0.0 <2.0.0` comparison conjunction.
- `*` any version.

Constraints separated by commas or whitespace form a conjunction. Pre-release versions are not supported.

## 7. Command line

```text
powang pkg init [--name NAME] [--version VERSION] [--registry URL]
powang pkg add NAME[@CONSTRAINT] [--path PATH] [--name NAME] [--no-install]
powang pkg remove NAME [NAME...] [--no-install]
powang pkg install [--locked] [--offline] [--force]
powang pkg update [NAME...]
powang pkg list
powang pkg tree
powang pkg search QUERY
powang pkg clean [--cache]
```

- `init` creates `powang.toml`.
- `add` updates the manifest and installs. A name without a constraint selects the latest registry version and writes a caret constraint. `--path` adds a path dependency.
- `remove` removes a direct dependency and installs the remaining graph.
- `install --locked` fails if the lock is missing or out of date. It never changes the lock.
- `install --offline` uses only the registry index and archive caches.
- `install --force` reinstalls extracted registry packages.
- `update` without names ignores the lock for every package. `update NAME` ignores the lock only for the named packages, including transitive packages.
- `list` prints locked packages and sources.
- `tree` prints the dependency tree.
- `search` queries the configured registry index.
- `clean` removes `.powang`. `clean --cache` also removes the global cache.

## 8. Runtime and checker integration

`load_package_config` finds the nearest `powang.toml` from the running file or the current directory.

When a current lock exists, it adds the package module roots to `state.module_search_paths`:

- Registry package: `.powang/packages/<name>/<version>`.
- Path package: the resolved source directory.

A package module is then imported with the normal syntax.

```po
use mathlib as *;
use utils as u;
```

`powang run` and file runs require a current lock when the manifest has dependencies. Missing locks, out-of-date locks and missing installed packages produce a `[PACKAGE ERROR]` with the install command.

The type checker uses the same module search paths through the module loader, so package calls are checked at the importing site.

## 9. LSP support

The LSP loads package configuration before diagnostics. A source file inside a package project resolves locked package imports and reports type errors at the importing call site. If package files are missing, the LSP reports the unresolved import instead of crashing.

## 10. Security

- Archive integrity uses SHA-256.
- Download size is capped at 256 MiB.
- HTTP downloads use a 30 second timeout.
- Tar extraction rejects absolute paths, path traversal, symbolic links, hard links and device entries.
- Extraction writes to a temporary directory and only replaces the installed package after validation.
- The cache is keyed by archive hash and registry URL.

## 11. Limitations

- Git dependencies are not supported.
- Prerelease versions are not supported.
- Only one version of a package can exist in a resolved graph.
- Registry packages may declare only registry dependencies.
- There is no publishing or authentication workflow.
- There are no dev, build or optional dependencies.
- There are no workspaces or monorepos.
- A path dependency must be rebuilt by running `powang pkg install` after its own manifest changes. The installer re-resolves when path packages are present.

## 12. Tests

Powang tests cover:

- Semver parsing and matching.
- Manifest read, write, validation and hashing.
- Transitive resolution and highest version selection.
- Lock reuse and updates.
- Conflicting constraints.
- Path dependencies and transitive registry dependencies.
- Integrity mismatches and unsafe archive paths.
- Locked and offline installs.
- CLI init, add, remove, install, update, list, tree, search and clean.
- File and project runs with package imports.
- Package-aware type checking.
- HTTP registry downloads.

LSP tests cover:

- Package diagnostics with a locked path dependency.

## 13. Acceptance criteria

- `powang pkg init` creates a valid manifest.
- `powang pkg add` updates the manifest, resolves dependencies and writes a lock.
- `powang pkg install` reproduces the lock and installs missing packages.
- `powang pkg update` selects newer versions while respecting constraints.
- Conflicting constraints produce a clear error.
- Registry archives are integrity checked and safely extracted.
- Path dependencies work without copying.
- `use name` resolves installed and path packages at runtime and in the checker.
- `powang run` requires a current lock when dependencies are declared.
- The LSP resolves locked package imports.
- The full powang test suite passes in normal mode and under `python -O`.
- The LSP test suite, smoke test, version check and vendored source check pass.
