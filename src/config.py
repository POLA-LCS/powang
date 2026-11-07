"""Project configuration and environment support for powang."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from .error import powang_error_format, powang_throw
from .lexer.token import LexerTokenType, ParserTokenType
from .error import powang_error_format, powang_throw
from .parser import Parser, ParserTokenType
from .powang_types import PowangProject

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None


_DEFAULT_EXTERNAL_MODULES = {
    "math",
    "stdlib_strings",
    "stdlib_json",
    "stdlib_url",
    "stdlib_env",
    "stdlib_time",
    "stdlib_crypto",
    "stdlib_http",
    "stdlib_http_server",
    "stdlib_http_router",
    "stdlib_log",
    "stdlib_host",
}


def _split_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _extract_value(node: Any) -> Any:
    if not isinstance(node, dict):
        return None
    node_type = node.get('type')
    if node_type == LexerTokenType.IDENTIFIER:
        if node.get('value') == 'true':
            return True
        if node.get('value') == 'false':
            return False
        return None
    if node_type == LexerTokenType.STRING_LITERAL:
        return node.get('value')
    if node_type == LexerTokenType.BOOLEAN_LITERAL:
        return bool(node.get('value'))
    if node_type == LexerTokenType.INTEGER_LITERAL:
        return int(node.get('value'))
    if node_type == ParserTokenType.INSTANTIATION:
        value = node.get('value')
        if not isinstance(value, dict):
            return None
        type_ref = value.get('type_ref')
        if not isinstance(type_ref, dict):
            return None
        name = type_ref.get('name')
        if name in ('arr', 'set'):
            items = []
            for argument in value.get('arguments', []):
                if not isinstance(argument, dict):
                    return None
                item = _extract_value(argument.get('value'))
                if item is None and argument.get('value', {}).get('type') != LexerTokenType.STRING_LITERAL:
                    return None
                items.append(item)
            return items
        return None
    if node_type == ParserTokenType.KEY_VALUE_PAIR:
        value = node.get('value')
        if not isinstance(value, dict):
            return None
        key = _extract_value(value.get('key'))
        item = _extract_value(value.get('value'))
        if not isinstance(key, str):
            return None
        return key, item
    return None


def _extract_project_config(program_ast: Any) -> dict[str, Any]:
    declaration = None
    for statement in program_ast if isinstance(program_ast, (list, tuple)) else []:
        if not isinstance(statement, dict):
            continue
        statement_type = statement.get('type')
        value = statement.get('value')
        if not isinstance(value, dict):
            continue
        if statement_type not in (ParserTokenType.DECLARATION_TYPED_VAR, ParserTokenType.DECLARATION_INTERPRET):
            continue
        identifier = value.get('identifier')
        if not isinstance(identifier, dict) or identifier.get('value') != 'project':
            continue
        type_node = value.get('type')
        if not isinstance(type_node, dict):
            continue
        type_name = type_node.get('value')
        if isinstance(type_name, dict):
            type_name = type_name.get('value')
        if type_name != 'Project':
            continue
        declaration = value
        break

    if declaration is None:
        raise powang_throw(powang_error_format(
            'USAGE', 'project', 'project.po must export project: Project',
        ))

    expression = declaration.get('expression')
    if not isinstance(expression, dict) or expression.get('type') != ParserTokenType.INSTANTIATION:
        raise powang_throw(powang_error_format(
            'USAGE', 'project', 'project must be initialized with a construction',
        ))

    expr_value = expression.get('value')
    if not isinstance(expr_value, dict):
        raise powang_throw(powang_error_format(
            'USAGE', 'project', 'project must be initialized with a construction',
        ))

    type_ref = expr_value.get('type_ref')
    type_name = type_ref.get('name') if isinstance(type_ref, dict) else None
    fields = ["modules", "paths", "logLevel", "allowSystem"]
    values: dict[str, Any] = {field: None for field in fields}

    arguments = expr_value.get('arguments', [])
    positional: list[Any] = []
    named: dict[str, Any] = {}
    for argument in arguments if isinstance(arguments, list) else []:
        if not isinstance(argument, dict):
            continue
        name = argument.get('name')
        argument_value = argument.get('value')
        if isinstance(name, str):
            extracted = _extract_value(argument_value)
            if extracted is None and not (isinstance(argument_value, dict) and argument_value.get('type') == LexerTokenType.STRING_LITERAL and argument_value.get('value') == ''):
                raise powang_throw(powang_error_format(
                    'USAGE', 'project', f"invalid value for field '{name}'",
                ))
            named[name] = extracted
        elif isinstance(argument_value, dict) and argument_value.get('type') == ParserTokenType.KEY_VALUE_PAIR:
            pair = argument_value.get('value')
            if not isinstance(pair, dict):
                continue
            key = _extract_value(pair.get('key'))
            if not isinstance(key, str):
                raise powang_throw(powang_error_format(
                    'USAGE', 'project', 'project fields must be named with strings',
                ))
            item = _extract_value(pair.get('value'))
            named[key] = item
        else:
            extracted = _extract_value(argument_value)
            positional.append(extracted)

    if type_name == 'Project':
        if positional:
            if len(positional) > len(fields):
                raise powang_throw(powang_error_format(
                    'USAGE', 'project', "Too many Project fields",
                ))
            for index, value in enumerate(positional):
                values[fields[index]] = value
        for name, value in named.items():
            if name not in values:
                raise powang_throw(powang_error_format(
                    'USAGE', 'project', f"Project has no field named '{name}'",
                ))
            values[name] = value
    elif type_name in ('tup', None):
        # Tuple sugar: .[modules >> [...], ...]
        for name, value in named.items():
            if name not in values:
                raise powang_throw(powang_error_format(
                    'USAGE', 'project', f"Project has no field named '{name}'",
                ))
            values[name] = value
        if positional:
            if len(positional) > len(fields):
                raise powang_throw(powang_error_format(
                    'USAGE', 'project', "Too many Project fields",
                ))
            for index, value in enumerate(positional):
                values[fields[index]] = value
    else:
        raise powang_throw(powang_error_format(
            'USAGE', 'project', "project must be a Project construction",
        ))

    modules = values["modules"] if values["modules"] is not None else []
    paths = values["paths"] if values["paths"] is not None else []
    log_level = values["logLevel"] if values["logLevel"] is not None else "info"
    allow_system = values["allowSystem"] if values["allowSystem"] is not None else False

    if not isinstance(modules, list) or any(not isinstance(item, str) for item in modules):
        raise powang_throw(powang_error_format(
            'USAGE', 'project', "Project.modules must be an array of strings",
        ))
    if not isinstance(paths, list) or any(not isinstance(item, str) for item in paths):
        raise powang_throw(powang_error_format(
            'USAGE', 'project', "Project.paths must be an array of strings",
        ))
    if not isinstance(log_level, str):
        raise powang_throw(powang_error_format(
            'USAGE', 'project', "Project.logLevel must be a string",
        ))
    if not isinstance(allow_system, bool):
        raise powang_throw(powang_error_format(
            'USAGE', 'project', "Project.allowSystem must be a boolean",
        ))

    return {
        "modules": modules,
        "paths": paths,
        "logLevel": log_level,
        "allowSystem": allow_system,
    }


def load_config(state: Any, base_path: Path | str | None = None) -> None:
    """Load legacy powang.toml and environment configuration."""
    state.allowed_extern_modules = set(_DEFAULT_EXTERNAL_MODULES)
    state.module_search_paths = []
    state.host_callbacks = {}

    config_path = None
    env_config = os.environ.get("POWANG_CONFIG")
    if env_config:
        config_path = Path(env_config)
    else:
        root = Path(base_path).resolve().parent if base_path else Path.cwd()
        candidate = root / "powang.toml"
        if candidate.exists():
            config_path = candidate

    if config_path is not None and config_path.exists() and tomllib is not None:
        with config_path.open("rb") as file:
            data = tomllib.load(file)
        extern = data.get("extern", {})
        paths = data.get("paths", {})
        host = data.get("host", {})
        state.allowed_extern_modules.update(_split_list(extern.get("modules")))
        for path in _split_list(paths.get("modules")):
            state.module_search_paths.append(Path(path).resolve())
        state.host_callbacks.update(host.get("callbacks", {}))

    env_modules = os.environ.get("POWANG_EXTERN_MODULES")
    if env_modules:
        state.allowed_extern_modules.update(_split_list(env_modules))

    env_paths = os.environ.get("POWANG_MODULE_PATH")
    if env_paths:
        for path in env_paths.split(os.pathsep):
            if path.strip():
                state.module_search_paths.append(Path(path).strip().resolve())

    if not state.module_search_paths:
        state.module_search_paths = [Path.cwd().resolve()]


def load_project_config(state: Any, base_path: Path | str | None = None) -> bool:
    root = Path(base_path).resolve().parent if base_path else Path.cwd()
    project_path = root / "project.po"
    if not project_path.exists():
        return False

    content = project_path.read_text(encoding="utf-8")
    from .parser import Parser, ParserTokenType
    from .powang_types import PowangProject
    program_ast = Parser(content, source_path=project_path).parse()

    if not program_ast or not isinstance(program_ast[0], dict):
        raise powang_throw(powang_error_format(
            'USAGE', 'project', "project.po must start with 'module project;'",
        ))
    first = program_ast[0]
    if first.get('type') != ParserTokenType.MODULE_DECLARATION:
        raise powang_throw(powang_error_format(
            'USAGE', 'project', "project.po must start with 'module project;'",
        ))
    first_value = first.get('value')
    if not isinstance(first_value, dict) or first_value.get('identifier', {}).get('value') != 'project':
        raise powang_throw(powang_error_format(
            'USAGE', 'project', "project.po must start with 'module project;'",
        ))

    config = _extract_project_config(program_ast)
    state.allowed_extern_modules.update(config["modules"])
    for path in config["paths"]:
        state.module_search_paths.append(Path(path).resolve())
    state.log_level = config["logLevel"]
    state.allow_system = config["allowSystem"]
    state.project_value = PowangProject(
        config["modules"],
        config["paths"],
        config["logLevel"],
        config["allowSystem"],
    )
    return True
    """Load extern and path configuration into interpreter state."""
    state.allowed_extern_modules = set(_DEFAULT_EXTERNAL_MODULES)
    state.module_search_paths = []
    state.host_callbacks = {}

    config_path = None
    env_config = os.environ.get("POWANG_CONFIG")
    if env_config:
        config_path = Path(env_config)
    else:
        root = Path(base_path).resolve().parent if base_path else Path.cwd()
        candidate = root / "powang.toml"
        if candidate.exists():
            config_path = candidate

    if config_path is not None and config_path.exists() and tomllib is not None:
        with config_path.open("rb") as file:
            data = tomllib.load(file)
        extern = data.get("extern", {})
        paths = data.get("paths", {})
        host = data.get("host", {})
        state.allowed_extern_modules.update(_split_list(extern.get("modules")))
        for path in _split_list(paths.get("modules")):
            state.module_search_paths.append(Path(path).resolve())
        state.host_callbacks.update(host.get("callbacks", {}))

    env_modules = os.environ.get("POWANG_EXTERN_MODULES")
    if env_modules:
        state.allowed_extern_modules.update(_split_list(env_modules))

    env_paths = os.environ.get("POWANG_MODULE_PATH")
    if env_paths:
        for path in env_paths.split(os.pathsep):
            if path.strip():
                state.module_search_paths.append(Path(path).strip().resolve())

    if not state.module_search_paths:
        state.module_search_paths = [Path.cwd().resolve()]
