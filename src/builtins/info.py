from ..powang_types import *
from ..error import *

def builtin_typeof(arg: PowangAny):
    if arg.type == PowangSome.type:
        return PowangString(arg.some)    
    return PowangString(arg.type)