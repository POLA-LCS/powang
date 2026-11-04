# Powang language support for Visual Studio Code

Syntax highlighting and language configuration for the Powang language.

## Install (local extension)

1. Open VS Code.
2. Press `Ctrl+Shift+P`, run `Developer: Install Extension from Location...`, and select this folder.
3. Reload the window.
4. Open any `.po` file. It should be recognized as `powang` and highlighted.

Alternatively, copy this folder into `~/.vscode/extensions/powang-0.2.0/` and reload.

## Language configuration

`language-configuration.json` provides:

- `##` line comments
- auto-closing brackets and quotes
- indentation rules based on braces

## LSP diagnostics and completion

The extension ships only the grammar. For diagnostics and completion, install the
**LSP Client** extension (marketplace id `lsp-client`) and add this to your
workspace `settings.json`:

```json
{
  "lsp.clients": [
    {
      "name": "powang",
      "command": ["python", "${workspaceFolder}/tools/powang_lsp.py"],
      "filetypes": ["powang"],
      "rootUri": "${workspaceFolder}"
    }
  ]
}
```

The server is started from the repository root so it can import `src`. It publishes
diagnostics from the parser and the gradual type checker and offers keyword and
builtin completion. Hover, rename and goto-definition are not yet implemented.
