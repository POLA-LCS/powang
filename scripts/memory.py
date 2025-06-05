from .types import *

SCOPE_STACK: list[str] = ['global']

MEMORY: dict[str, dict[str, PowangAny]] = {
    'global': {
        'nice': PowangNumber(69.0, const=True),
        'newl': PowangString('\n', const=True),
        'tab': PowangString('\t', const=True),
        'false': PowangNumber(0.0, const=True),
        'true': PowangNumber(1.0, const=True),

        'false_struct': PowangStruct({}, {
            'bool': PowangCallable(0, 0, False, lambda: PowangNumber(0.0))
        }),
        
        'true_struct': PowangStruct({}, {
            'bool': PowangCallable(0, 0, False, lambda: PowangNumber(1.0))
        })
    }
}

def get_memory(name: str) -> (PowangAny | None):
    if (value := MEMORY[SCOPE_STACK[-1]].get(name)) is not None:
        return value
    return MEMORY['global'].get(name)

def set_memory(name: str, value: PowangAny):
    MEMORY[SCOPE_STACK[-1]][name] = value