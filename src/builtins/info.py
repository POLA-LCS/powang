from ..powang_types import *
from ..error import *

def builtin_typeof(arg: PowangAny):
    if arg.type == PowangAnyType.type:
        return PowangString(arg.any)
    if arg.type == PowangObjectType.type:
        ## User defined types carry their concrete name, fall back to 'object'
        return PowangString(getattr(arg, 'type_name', '') or PowangObjectType.type_name)
    return PowangString(arg.type)


def _deep_type_name(arg: PowangAny, depth: int = 0) -> str:
    if depth > 64:
        return PowangAnyType.type
    if arg.type == PowangAnyType.type:
        concrete = getattr(arg, 'concrete_value', None)
        if concrete is not None:
            return _deep_type_name(concrete, depth + 1)
        return arg.any or PowangAnyType.type
    if arg.type == PowangObjectType.type:
        return arg.type_name or PowangObjectType.type_name
    if arg.type == PowangArray.type:
        element_types: list[str] = []
        for element in arg.data:
            element_type = _deep_type_name(element, depth + 1)
            if element_type not in element_types:
                element_types.append(element_type)
        if not element_types:
            return f'{PowangArray.type}[{PowangAnyType.type}]'
        return f'{PowangArray.type}[{" | ".join(element_types)}]'
    if arg.type == PowangHandle.type:
        return 'handle'
    if arg.type == PowangHandle.type:
        return 'handle'
    if arg.type == PowangProject.type:
        return 'Project'
    if arg.type == PowangTuple.type:
        if not arg.data:
            return PowangTuple.type
        return f'{PowangTuple.type}[' + ', '.join(
            _deep_type_name(element, depth + 1) for element in arg.data
        ) + ']'
    if arg.type == PowangSet.type:
        element_types: list[str] = []
        for element in arg.data.keys():
            element_type = _deep_type_name(element, depth + 1)
            if element_type not in element_types:
                element_types.append(element_type)
        if not element_types:
            return f'{PowangSet.type}[{PowangAnyType.type}]'
        return f'{PowangSet.type}[{" | ".join(element_types)}]'
    return arg.type


def builtin_typedeep(arg: PowangAny):
    """Structural type of a value, including array and tuple elements."""
    return PowangString(_deep_type_name(arg))
