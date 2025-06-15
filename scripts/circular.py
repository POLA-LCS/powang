# ====== GENERAL =========
def get_powang_callable(name: str):
    from .runtime import BUILTINS, KEYWORDS
    if (func := BUILTINS.get(name)) is not None:
        return func
    elif (func := KEYWORDS.get(name)) is not None:
        return func
    # TODO: USER DEFINED FUNCTIONS
    return None

def circular_process_value(indent: int, rest: list):
    from .interpret import process_values
    return process_values(indent, rest)

def circular_interpret_line(indent: int, line: list):
    from .interpret import interpret_line
    return interpret_line(indent, line)