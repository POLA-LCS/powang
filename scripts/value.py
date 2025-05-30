
# POLANG TYPE SUPPORT
class Types:
    Number = float
    String = str
    List = list
    Any_t = Number | String | List | None

    map = {
        Number: 'number',
        String: 'string',
        List: 'list',
        Any_t: 'any',
        None: 'none'
    }

# A powang value representation
class Value:
    def __init__(self, value: Types.Any_t, const: bool):
        if isinstance(value, int):
            value = float(value)
        self.value = value
        self.const = const

    @property
    def type(self) -> str:
        return Types.map[type(self.value)]

    def __repr__(self) -> str:
        return f'({self.value}: {self.type})'

    # """""""PYTHONIC""""""""" DEBUG
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