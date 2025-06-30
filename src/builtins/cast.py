from ..powang_types import *
from ..error import *

def explicit_cast_string(left: PowangAny):
    if not left.defined:
        return PowangString(f'<{left.type}: undefined>')
    if not left.weak.has_value or left.type == PowangNova.type:
        return PowangString('nova')

    if (cast_result := PowangString.cast(left)) is not None:
        return cast_result

    if left.type == PowangSome.type:
        assert (cast_result := explicit_cast_string(PowangTypeMap(
            left.some
            if   left.some is not None
            else PowangNova.type
        )(left.data))) is not None, powang_error_format_invalid_cast(
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
            cast_result = explicit_cast_string(item)
            if cast_result is None: return None
            result_list.append(cast_result.data)
        return PowangString('[' + ', '.join(result_list) + ']')
    if left.type == PowangMap.type:
        result_dict: dict[str, str] = {}
        for key, value in left.data.items():
            key_cast = explicit_cast_string(key)
            if key_cast is None: return None

            value_cast = explicit_cast_string(value)
            if value_cast is None: return None

            result_dict[key_cast.data] = value_cast.data
        return PowangString('[' + ', '.join(' => '.join([key, value]) for key, value in result_dict.items()) + ']')
    return None

def explicit_cast_integer(left: PowangAny):
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

def explicit_cast_number(left: PowangAny):
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

def explicit_cast_array(left: PowangAny):
    assert left.defined, powang_error_undefined_reference('explicit cast', 'left operand')
    if (cast_result := PowangArray.cast(left)) is not None:
        return cast_result
    if not left.weak.has_value or left.type == PowangNova.type:
        return PowangArray()
    if left.type == PowangString.type:
        return PowangArray([PowangString(char) for char in left.data])
    return None

def explicit_cast_map(left: PowangAny):
    assert left.defined, powang_error_undefined_reference('explicit cast', 'left operand')
    if (cast_result := PowangMap.cast(left)) is not None:
        return cast_result

def explicit_cast_some(left: PowangAny):
    return PowangSome.cast(left)

def explicit_cast(type: str, left: PowangAny):
    match type:
        case PowangInteger.type:
            return explicit_cast_integer(left)
        case PowangNumber.type:
            return explicit_cast_number(left)
        case PowangString.type:
            return explicit_cast_string(left)
        case PowangArray.type:
            return explicit_cast_array(left)
        case PowangSome.type:
            return explicit_cast_some(left)
    return None