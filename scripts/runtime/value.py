from ..types import *

# POWANG VALUE REPRESENTATION
class Value:
    def __init__(self, value: ANY, const: bool):
        if isinstance(value, int):
            value = float(value)
        self.value = value
        self.const = const

    @property
    def type(self) -> (str | None):
        return type_to_str(type(self.value))

    def __repr__(self) -> str:
        return f'({self.value}: {self.type})'

    # """""""PYTHONIC""""""""" DEBUG
    def __str__(self) -> str:
        if self.value is None:
            return 'none'
        return str(self.value)