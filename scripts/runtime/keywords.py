from ..types import *
from ..types import PowangCallable
from ..lexing.token import *
from ..error import *

from .keywords_impl import *

KEYWORDS: dict[str, PowangCallable] = {
    'if': PowangCallable(2, 2, True, keyword_if),
    'end': PowangCallable(0, 0, False, lambda: PowangNov()),
    'var': PowangCallable(2, 2, False, keyword_var),
    'del': PowangCallable(1, 1, True, keyword_del)
}

