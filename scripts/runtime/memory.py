from .value import Value

STACK = ['global']

MEMORY: dict[str, dict[str, Value]] = {
    'global': {
        'nice': Value(69.0, True),
        'newl': Value('\n', False)
    }
}

def get_memory(name: str) -> (Value | None):
    if (value := MEMORY[STACK[-1]].get(name)) is not None:
        return value
    return MEMORY['global'].get(name)