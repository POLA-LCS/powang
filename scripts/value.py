from typing import Self

# POLANG TYPE SUPPORT
class Types:
    Number = float
    String = str
    List = list
    Any = Number | String | List

# A powang value representation
class Value:
    def __init__(self, value: Types.Any | Self, const: bool):
        self.value = value
        self.const = const

    @property
    def type(self):
        if isinstance(self.value, (int, float)):
            return Types.Number
        if isinstance(self.value, str):
            return Types.String
        if isinstance(self.value, list):
            return Types.List
        return Types.Any

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