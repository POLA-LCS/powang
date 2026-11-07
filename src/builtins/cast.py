from ..powang_types import *
from ..error import *
from .. import typespec as ts

def explicitCastString(left: PowangAny) -> Optional[PowangString]:
    if not left.defined:
        return PowangString(f'<{left.type if left.type != PowangObjectType.type else left.type_name}: undefined>')
    if not left.weak.has_value or left.type == PowangNova.type:
        return PowangString('nova')

    if (cast_result := PowangString.cast(left)) is not None:
        return cast_result

    if left.type == PowangAnyType.type:
        concrete = PowangUnwrapAny(left)
        if concrete is not left:
            casted_concrete = explicitCastString(concrete)
            if casted_concrete is not None:
                return casted_concrete
            if concrete.type == PowangObjectType.type:
                return PowangString(f"<type: {concrete.type_name}>")
            return None
        defined_some = PowangUnwrapAny(left)
        if defined_some is left:
            return None
        cast_result = explicitCastString(defined_some)
        if cast_result is None:
            raise powang_throw(powang_error_invalid_cast(
                None, PowangString.type, left.type, True
            ))
        return cast_result
    if left.type == PowangInteger.type or left.type == PowangNumber.type:
        return PowangString(str(left.data))
    if left.type == PowangBoolean.type:
        return PowangString('true' if left.data else 'false')
    if left.type == PowangArray.type:
        result_list: list[str] = []
        for item in left.data:
            cast_result = explicitCastString(item)
            if cast_result is None: return None
            result_list.append(cast_result.data)
        return PowangString('[' + ', '.join(result_list) + ']')
    if left.type == PowangSet.type:
        result_list: list[str] = []
        for item in left.data.keys():
            cast_result = explicitCastString(item)
            if cast_result is None:
                return None
            result_list.append(cast_result.data)
        return PowangString('[/' + ', '.join(result_list) + ']')
    if left.type == PowangHandle.type:
        return PowangString(f"<handle: {left.data}>")
    if left.type == PowangHandle.type:
        return PowangString(f"<handle: {left.data}>")
    if left.type == PowangProject.type:
        return PowangString("<Project>")
    if left.type == PowangTuple.type:
        result_list: list[str] = []
        for item in left.data:
            cast_result = explicitCastString(item)
            if cast_result is None: return None
            result_list.append(cast_result.data)
        return PowangString('[' + ', '.join(result_list) + ']')
    if left.type == PowangMap.type:
        result_dict: dict[str, str] = {}
        for key, value in left.data.items():
            key_cast = explicitCastString(key)
            if key_cast is None: return None

            value_cast = explicitCastString(value)
            if value_cast is None: return None

            result_dict[key_cast.data] = value_cast.data
        return PowangString('[' + ', '.join(' >> '.join([key, value]) for key, value in result_dict.items()) + ']')
    if left.type == PowangObjectType.type and getattr(left, 'is_enum', False):
        variant_name = left.data.get('name') if isinstance(left.data, dict) else None
        if isinstance(variant_name, PowangString):
            return PowangString(f'<{left.type_name}: {variant_name.data}>')
        return PowangString(f'<{left.type_name}>')
    return None

def explicitCastInteger(left: PowangAny) -> Optional[PowangInteger]:
    assert left.defined, powang_error_undefined_reference('explicit cast', 'left operand')
    if (cast_result := PowangInteger.cast(left)) is not None:
        return cast_result
    if not left.weak.has_value or left.type == PowangNova.type:
        return PowangInteger()
    if left.type == PowangString.type:
        try:
            return PowangInteger(int(left.data))
        except ValueError:
            assert powang_error_format("RUNTIME", 'explicit cast', "Invalid int string", [
                f"\"{left.data}\""
            ])
    return PowangInteger.cast(left)

def explicitCastNumber(left: PowangAny) -> Optional[PowangNumber]:
    assert left.defined, powang_error_undefined_reference('explicit cast', 'left operand')

    if (cast_result := PowangNumber.cast(left)) is not None:
        return cast_result
    if not left.weak.has_value or left.type == PowangNova.type:
        return PowangNumber()
    if left.type == PowangString.type:
        try:
            return PowangNumber(float(left.data))
        except ValueError:
            assert powang_error_format("RUNTIME", 'explicit cast', "Invalid num string", [
                f"\"{left.data}\""
            ])
    return None

def explicitCastArray(left: PowangAny) -> Optional[PowangArray]:
    assert left.defined, powang_error_undefined_reference('explicit cast', 'left operand')
    if (cast_result := PowangArray.cast(left)) is not None:
        return cast_result
    if not left.weak.has_value or left.type == PowangNova.type:
        return PowangArray()
    if left.type == PowangString.type:
        return PowangArray([PowangString(char) for char in left.data])
    if left.type == PowangTuple.type:
        return PowangArray(list(left.data))
    if left.type == PowangMap.type:
        result: list[PowangAny] = []
        for key, value in left.data.items():
            result.append(PowangTuple([key, value]))
        return PowangArray(result)
    return None


def explicitCastSet(left: PowangAny) -> Optional[PowangSet]:
    assert left.defined, powang_error_undefined_reference('explicit cast', 'left operand')
    if (cast_result := PowangSet.cast(left)) is not None:
        return cast_result
    if not left.weak.has_value or left.type == PowangNova.type:
        return PowangSet()
    return None


def explicitCastTuple(left: PowangAny) -> Optional[PowangTuple]:
    assert left.defined, powang_error_undefined_reference('explicit cast', 'left operand')
    if (cast_result := PowangTuple.cast(left)) is not None:
        return cast_result
    if not left.weak.has_value or left.type == PowangNova.type:
        return PowangTuple()
    if left.type == PowangArray.type:
        return PowangTuple(list(left.data))
    if left.type == PowangMap.type:
        result: list[PowangAny] = []
        for key, value in left.data.items():
            result.append(PowangTuple([key, value]))
        return PowangTuple(result)
    return None

def explicitCastMap(left: PowangAny) -> Optional[PowangMap]:
    assert left.defined, powang_error_undefined_reference('explicit cast', 'left operand')
    if (cast_result := PowangMap.cast(left)) is not None:
        return cast_result

def _source_items(left: PowangAny):
    """Flatten arr, tup and map into a sequence of values."""
    if left.type in (PowangArray.type, PowangTuple.type):
        return list(left.data)
    if left.type == PowangMap.type:
        return [PowangTuple([key, value]) for key, value in left.data.items()]
    if left.type == PowangString.type:
        return [PowangString(char) for char in left.data]
    return None


def _source_entries(left: PowangAny):
    """Flatten arr, tup and map into key value pairs."""
    if left.type == PowangMap.type:
        return list(left.data.items())
    items = _source_items(left)
    if items is None:
        return None
    entries = []
    for index, item in enumerate(items):
        if item.type not in (PowangArray.type, PowangTuple.type) or len(item.data) < 2:
            raise powang_throw(powang_error_format(
                'RUNTIME', 'explicit cast', 'array to map requires pairs', [
                    f'element {index} is {item.type}',
                ]))
        entries.append((item.data[0], item.data[1]))
    return entries


def _element_specs(target: ts.TypeSpec, count: int):
    if not target.args:
        return [ts.TypeSpec(name='any')] * count
    head = ts.HEADS.get(target.name)
    if head is not None and head.shape is ts.Shape.SEQUENCE and target.name != PowangTuple.type:
        # arr[element] applies the same element spec to every item.
        return [target.args[0]] * count
    if target.rest:
        fixed = target.args[:-1]
        tail = target.args[-1]
        if count < len(fixed):
            raise powang_throw(powang_error_format(
                'RUNTIME', 'explicit cast', 'tuple arity mismatch', [
                    f'expected at least {len(fixed)} elements',
                    f'but {count} were given',
                ]))
        return list(fixed) + [tail] * (count - len(fixed))
    if count != len(target.args):
        raise powang_throw(powang_error_format(
            'RUNTIME', 'explicit cast', 'tuple arity mismatch', [
                f'expected {len(target.args)} elements',
                f'but {count} were given',
            ]))
    return list(target.args)


def cast_to_spec(left: PowangAny, target: ts.TypeSpec, mode: str = 'explicit', depth: int = 0):
    """Recursive structural cast driven by the target TypeSpec."""
    if depth > 64:
        raise powang_throw(powang_error_format(
            'RUNTIME', 'explicit cast', 'cast nesting too deep', []))
    if left.type == PowangAnyType.type:
        left = PowangUnwrapAny(left)
    if left.type == PowangReference.type:
        left = left.get()
    if not left.defined:
        if target.name == PowangString.type:
            return PowangString(f'<{ts.render(target)}: undefined>')
        raise powang_throw(powang_error_undefined_reference('explicit cast', 'left operand'))
    if left.type == PowangNova.type or not left.weak.has_value:
        return _nova_to_spec(target)

    if target.name == 'any':
        return PowangCopyConstruct(left)

    if target.kind is ts.Kind.FUNCTION:
        if left.type == PowangFunction.type:
            return PowangCopyConstruct(left)
        return None

    if target.kind is ts.Kind.UNION:
        for branch in target.args:
            try:
                converted = cast_to_spec(left, branch, mode, depth + 1)
            except PowangError:
                continue
            if converted is not None:
                return converted
        return None

    if target.nominal:
        return None

    head = ts.HEADS.get(target.name)
    if head is None:
        return None

    if head.shape is ts.Shape.SEQUENCE:
        items = _source_items(left)
        if items is None:
            items = _scalar_sequence(left)
        if items is None:
            return None
        if not target.args:
            if target.name == PowangTuple.type:
                return PowangTuple(list(items))
            return PowangArray(list(items))
        specs = _element_specs(target, len(items))
        converted = [cast_to_spec(item, spec, mode, depth + 1) for item, spec in zip(items, specs)]
        if any(item is None for item in converted):
            return None
        if target.name == PowangTuple.type:
            return PowangTuple(converted)
        return PowangArray(converted)

    if head.shape is ts.Shape.MAPPING:
        entries = _source_entries(left)
        if entries is None:
            return None
        if not target.args:
            return PowangMap({key: value for key, value in entries})
        key_spec = target.args[0] if len(target.args) > 0 else ts.TypeSpec(name='any')
        value_spec = target.args[1] if len(target.args) > 1 else ts.TypeSpec(name='any')
        result = PowangMap()
        for key, value in entries:
            converted_key = cast_to_spec(key, key_spec, mode, depth + 1)
            converted_value = cast_to_spec(value, value_spec, mode, depth + 1)
            if converted_key is None or converted_value is None:
                return None
            result.data[converted_key] = converted_value
        return result

    return explicitCast(target.name, left)


def _scalar_sequence(left: PowangAny):
    if left.type in (PowangString.type, PowangInteger.type, PowangNumber.type):
        return [left]
    return None


def _nova_to_spec(target: ts.TypeSpec):
    if target.weak or target.name == PowangNova.type:
        return PowangNova()
    if target.kind is ts.Kind.UNION:
        for branch in target.args:
            converted = _nova_to_spec(branch)
            if converted is not None:
                return converted
        return None
    head = ts.HEADS.get(target.name)
    if head is None:
        return None
    if head.shape is ts.Shape.SEQUENCE:
        return PowangTuple() if target.name == PowangTuple.type else PowangArray()
    if head.shape is ts.Shape.MAPPING:
        return PowangMap()
    return explicitCast(target.name, PowangNova())


def can_cast(target: ts.TypeSpec, source_type: str) -> bool:
    if target.kind is ts.Kind.UNION:
        return any(can_cast(branch, source_type) for branch in target.args)
    head = ts.HEADS.get(target.name)
    if head is None:
        return False
    if head.shape in (ts.Shape.SEQUENCE, ts.Shape.MAPPING):
        return source_type in (
            PowangArray.type, PowangTuple.type, PowangMap.type, PowangString.type,
        )
    return source_type in (
        PowangNova.type, PowangAnyType.type, PowangBoolean.type,
        PowangInteger.type, PowangNumber.type, PowangString.type,
        PowangArray.type, PowangTuple.type, PowangMap.type,
        PowangErrorValue.type, PowangObjectType.type,
    )


def explicitCast(type, left: PowangAny):
    if isinstance(type, ts.TypeSpec):
        return cast_to_spec(left, type)
    match type:
        case PowangBoolean.type:
            return PowangBoolean.cast(left)
        case PowangInteger.type:
            return explicitCastInteger(left)
        case PowangNumber.type:
            return explicitCastNumber(left)
        case PowangString.type:
            return explicitCastString(left)
        case PowangArray.type:
            return explicitCastArray(left)
        case PowangMap.type:
            return explicitCastMap(left) or PowangMap.cast(left)
        case PowangSet.type:
            return explicitCastSet(left)
        case PowangTuple.type:
            return explicitCastTuple(left)
    return None