from ..types import InstructionFormat
from ..lexing.token import *
from ..error import *

from .keywords_impl import *

KEYWORDS: dict[str, InstructionFormat] = {
    # ====== VARIABLE =========
    'var':  (2, 2, False, keyword_var ),
    'def':  (2, 2, False, keyword_def),
    'set':  (2, 2, True, keyword_set),
    
    # ====== CONTROL =========
    'if':   (1, 4, True , keyword_if  ),
    'else': (0, 1, False, keyword_else_else_if),
    'ends':  (0, 0, False, keyword_end),
    #'del':  (1, 1, True , keyword_del )
    
    'label': (1, 1, False, keyword_label),
    'goto': (0, 1, False, keyword_goto)
}