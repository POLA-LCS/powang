from ..powang_types import *
from ..error import *

def explicitCastString(left: PowangAny) -> Optional[PowangString]:
    if not left.defined:
        return PowangString(f'<{left.type if left.type != PowangObjectType.type else left.type_name}: undefined>')
    if not left.weak.has_value or left.type == PowangNova.type:
        return PowangString('nova')

    if (cast_result := PowangString.cast(left)) is not None:
        return cast_result

    if left.type == PowangSome.type:
        defined_some = PowangTypeMap(left.some)(left.data)
        assert (cast_result := explicitCastString(defined_some)) is not None, powang_error_invalid_cast(
            None, PowangString.type, left.type, True
        )
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
    if left.type == PowangMap.type:
        result_dict: dict[str, str] = {}
        for key, value in left.data.items():
            key_cast = explicitCastString(key)
            if key_cast is None: return None

            value_cast = explicitCastString(value)
            if value_cast is None: return None

            result_dict[key_cast.data] = value_cast.data
        return PowangString('[' + ', '.join(' >> '.join([key, value]) for key, value in result_dict.items()) + ']')
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
            assert powang_error_format("RUNTIME", 'explicit cast', "Invalid integer string", [
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
            assert powang_error_format("RUNTIME", 'explicit cast', "Invalid number string", [
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
    return None

def explicitCastMap(left: PowangAny) -> Optional[PowangMap]:
    assert left.defined, powang_error_undefined_reference('explicit cast', 'left operand')
    if (cast_result := PowangMap.cast(left)) is not None:
        return cast_result

def explicitCast(type: str, left: PowangAny):
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
            return PowangMap.cast(left)
    return None