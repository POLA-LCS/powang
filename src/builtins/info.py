from ..powang_types import *
from ..error import *

def builtin_typeof(arg: PowangAny):
    if arg.type == PowangSome.type:
        return PowangString(arg.some)
    if arg.type == PowangObjectType.type:
        ## User defined types carry their concrete name, fall back to 'object'
        return PowangString(getattr(arg, 'type_name', '') or PowangObjectType.type_name)
    return PowangString(arg.type)