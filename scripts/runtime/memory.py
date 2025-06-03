from .types import *

STACK = ['global']

MEMORY: dict[str, dict[str, PolangAny]] = {
    'global': {
        'nice': PolangNumber(69.0, const=True),
        'newl': PolangString('\n', const=True)
    }
}

def get_memory(name: str) -> (PolangAny | None):
    if (value := MEMORY[STACK[-1]].get(name)) is not None:
        return value
    return MEMORY['global'].get(name)