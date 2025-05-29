# POLANG TYPE SUPPORT
class Types:
    Number = int | float
    Any = str | Number | list | None
    STRING = 'string'
    NUMBER = 'number'
    LIST = 'list'
    NONE = 'none'
    ANY = 'any'

def get_number_from_word(number: str) -> (Types.Number | None):
    try:
        num = float(number)
        return integer if (integer := int(num)) == num else num
    except ValueError:
        return None

# A powang value representation
class Value:
    def __init__(self, value: Types.Any, const: bool):
        self.value = value
        self.const = const

    @property
    def type(self):
        if self.value is None:
            return Types.NONE
        if isinstance(self.value, (int, float)):
            return Types.NUMBER
        if isinstance(self.value, str):
            return Types.STRING
        if isinstance(self.value, list):
            return Types.LIST
        return Types.ANY

    def __repr__(self) -> str:
        return f'({self.value}: {self.type})'

    def __str__(self) -> str:
        if self.value is None:
            return 'none'
        return str(self.value)

class Macro:
    def __init__(self, name: str, argc: int, code: list[str] = []):
        self.name = name
        self.argc = argc
        self.code = code

    def __repr__(self) -> str:
        return f'{self.name}({self.argc})[{len(self.code)}]'