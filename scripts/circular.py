
def get_scope_name():
    from .memory import SCOPE_STACK
    return SCOPE_STACK[-1]

def get_powang_callable(name: str):
    from .instructions import INSTRUCTIONS, KEYWORDS
    if (func := INSTRUCTIONS.get(name)) is not None:
        return func
    elif (func := KEYWORDS.get(name)) is not None:
        return func
    return None

def circular_interpret_line(line: list):
    from .interpret import interpret_line
    return interpret_line(line)