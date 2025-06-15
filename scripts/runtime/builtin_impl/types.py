from ...types import PowangAny, PowangString

def builtin_type(value: PowangAny):
    return PowangString(value.type)