from .types import *

MEMORY = MemoryScopeHandler({
    'nice': PowangNumber(69.0, const=True),
    'newl': PowangString('\n', const=True),
})

SCOPE_LABELS: dict[str, int] = {}
