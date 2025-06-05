from typing import Union, Literal, Any, Self, Callable
from .error import error_logic

class PolangType_Base:
    type: Any = None
    
    def __init__(self, data, *, const: bool = False):
        self.data = data
        self.const = const

    def has(self, name: str):
        try:
            self.__getattribute__(name)
            return True
        except AttributeError:
            return False

    def __repr__(self):
        return f'PolangType({self.type} {'const' if self.const else 'mutable'}: {self.data})'
    

# ====== NUMBER =========
class PolangNumber(PolangType_Base):
    data: float
    type: Literal['number'] = 'number'
    def __init__(self, data: float, *,
        const: bool = False
    ):
        super().__init__(data, const=const)
        assert isinstance(self.data, float), error_logic(
            "I'm sorry, development error :(", [
                f"Somehow a {type(self.data)} is trying to construct a PolangNumber",
                "PolangNumber only accepts float types"
        ])
        
    # ====== Number
    def addition_number(self, rhs: Self):
        return PolangNumber(self.data + rhs.data)

    def substraction_number(self, rhs: Self):
        return PolangNumber(self.data - rhs.data)

    def multiplication_number(self, rhs: Self):
        return PolangNumber(self.data * rhs.data)

    def division_number(self, rhs: Self):
        return PolangNumber(self.data / rhs.data)

    # ====== String
    def addition_string(self, rhs: 'PolangString'):
        return PolangNumber(self.data + len(rhs.data))

    def substraction_string(self, rhs: 'PolangString'):
        """LEFT HAND SIDE"""
        return PolangString(rhs.data[self.data:])

    def multiplication_string(self, rhs: 'PolangString'):
        return rhs.multiplication_number(self)

    # ====== List
    def multiplication_list(self, rhs: 'PolangList'):
        return rhs.multiplication_number(self)

# ====== STRING =========
class PolangString(PolangType_Base):
    data: str
    type: Literal['string'] = 'string'
    def __init__(self, data: str, *,
        const: bool = False
    ):
        super().__init__(data, const=const)

    def addition_string(self, rhs: Self):
        """ string + string = APPEND """
        return PolangString(self.data + rhs.data)

    def substraction_string(self, rhs: Self):
        """ string - string = REMOVE """
        return PolangString(self.data.replace(rhs.data, '', 1))

    def division_string(self, rhs: Self):
        """ string / string = SPLIT """
        return PolangList([PolangString(part) for part in self.data.split(rhs.data)])
    
    def multiplication_number(self, rhs: PolangNumber):
        """ string * number = REPEATED APPEND """
        return PolangString(self.data * int(rhs.data))
    
    def substraction_number(self, rhs: PolangNumber):
        """ string - number = string[:-number] """
        return PolangString(self.data[:-int(rhs.data)])

    def division_number(self, rhs: PolangNumber):
        """ string / number = SPLIT BY STEPS"""
        result: list[PolangAny] = []
        record = ''
        for i, char in enumerate(self.data):
            if i and i % int(rhs.data) == 0:
                result.append(PolangString(record))
                record = char
            else:
                record += char
        if len(record) > 0:
            result.append(PolangString(record))
        return PolangList(result)
    

# ====== LIST =========
class PolangList(PolangType_Base):
    data: list['PolangAny']
    type: Literal['list'] = 'list'
    def __init__(self, data: list['PolangAny'], *,
        const: bool = False
    ):
        super().__init__(data, const=const)
        
    # ====== List
    def addition_list(self, list: Self):
        return PolangList(self.data + list.data)

    # ====== Number
    def multiplication_number(self, rhs: PolangNumber):
        return PolangList(self.data * int(rhs.data))
    
    def addition_number(self, rhs: PolangNumber):
        return PolangList(self.data + [rhs])

    # ====== String
    def addition_string(self, rhs: PolangString):
        return PolangList(self.data + [rhs])

# ====== STRUCT ========= TODO
class PolangStruct(PolangType_Base):
    data: dict[str, 'PolangAny']
    type: Literal['struct'] = 'struct'
    def __init__(self, data: dict[str, 'PolangAny'], *,
        const: bool = False
    ):
        super().__init__(data, const=const)
        
    def has(self, name: str):
        return False # not implemented

# ====== NOV =========
class PolangNov(PolangType_Base):
    data: None
    type: Literal['nov'] = 'nov'
    def __init__(self):
        super().__init__(None)

    def has(self, name: str):
        return False # not implemented

# ====== ANY =========
PolangAny = Union[
    PolangNov,
    PolangNumber,
    PolangString,
    PolangList,
    PolangStruct,
]

# ====== ERROR =========
class PolangError(PolangType_Base):
    data: tuple[str, str, list[str]]
    type: Literal['error'] = 'error'
    def __init__(self, data: tuple[str, str, list[str]]):
        super().__init__(data, const=True)
        
def deduce_polang_type(x, *, const: bool = False):
    if isinstance(x, (int, float)):
        return PolangNumber(x, const=const)
    elif isinstance(x, str):
        return PolangString(x, const=const)
    elif isinstance(x, list):
        return PolangList(x, const=const)
    elif isinstance(x, object):
        return PolangStruct(x.__dict__, const=const)
    elif isinstance(x, BaseException):
        return PolangError(x.args)
    elif x is None:
        return PolangNov()