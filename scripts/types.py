from types import NoneType

# POWANG TO PYTHON TYPE SUPPORT

NUMBER = float
STRING = str
LIST   = list
NOV    = NoneType
ANY    = NUMBER | STRING | LIST | NOV

def type_to_str(type) -> (str | None):
    return {
        NUMBER: 'number',
        STRING: 'string',
        LIST:   'list',
        NOV:    'nov',
        ANY:    'any',
    }.get(type, None)