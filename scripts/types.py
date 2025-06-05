from typing import Union, Literal, Any, Self, Callable
from .error import error_logic

class PowangType_Base:
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
        return f'PowangType({self.type} {'const' if self.const else 'mutable'}: {self.data})'
    

# ====== NUMBER =========
class PowangNumber(PowangType_Base):
    data: float
    type: Literal['number'] = 'number'
    def __init__(self, data: float, *,
        const: bool = False
    ):
        super().__init__(data, const=const)
        assert isinstance(self.data, float), error_logic(
            "I'm sorry, development error :(", [
                f"Somehow a {type(self.data)} is trying to construct a PowangNumber",
                "PowangNumber only accepts float types"
        ])
        
    # ====== Number
    def addition_number(self, rhs: Self):
        return PowangNumber(self.data + rhs.data)

    def substraction_number(self, rhs: Self):
        return PowangNumber(self.data - rhs.data)

    def multiplication_number(self, rhs: Self):
        return PowangNumber(self.data * rhs.data)

    def division_number(self, rhs: Self):
        return PowangNumber(self.data / rhs.data)
    
    # ====== ========= Comparisson
    def equal_number(self, rhs: Self):
        return self.data == rhs.data

    def equal_string(self, rhs: Self):
        return self.data

    # ====== String
    def addition_string(self, rhs: 'PowangString'):
        return PowangNumber(self.data + len(rhs.data))

    def substraction_string(self, rhs: 'PowangString'):
        """LEFT HAND SIDE"""
        return PowangString(rhs.data[self.data:])

    def multiplication_string(self, rhs: 'PowangString'):
        return rhs.multiplication_number(self)

    # ====== List
    def multiplication_list(self, rhs: 'PowangList'):
        return rhs.multiplication_number(self)

# ====== STRING =========
class PowangString(PowangType_Base):
    data: str
    type: Literal['string'] = 'string'
    def __init__(self, data: str, *,
        const: bool = False
    ):
        super().__init__(data, const=const)

    def addition_string(self, rhs: Self):
        """ string + string = APPEND """
        return PowangString(self.data + rhs.data)

    def substraction_string(self, rhs: Self):
        """ string - string = REMOVE """
        return PowangString(self.data.replace(rhs.data, '', 1))

    def division_string(self, rhs: Self):
        """ string / string = SPLIT """
        return PowangList([PowangString(part) for part in self.data.split(rhs.data)])
    
    def multiplication_number(self, rhs: PowangNumber):
        """ string * number = REPEATED APPEND """
        return PowangString(self.data * int(rhs.data))
    
    def substraction_number(self, rhs: PowangNumber):
        """ string - number = string[:-number] """
        return PowangString(self.data[:-int(rhs.data)])

    def division_number(self, rhs: PowangNumber):
        """ string / number = SPLIT BY STEPS"""
        result: list[PowangAny] = []
        record = ''
        for i, char in enumerate(self.data):
            if i and i % int(rhs.data) == 0:
                result.append(PowangString(record))
                record = char
            else:
                record += char
        if len(record) > 0:
            result.append(PowangString(record))
        return PowangList(result)
    

# ====== LIST =========
class PowangList(PowangType_Base):
    data: list['PowangAny']
    type: Literal['list'] = 'list'
    def __init__(self, data: list['PowangAny'], *,
        const: bool = False
    ):
        super().__init__(data, const=const)
        
    # ====== List
    def addition_list(self, list: Self):
        return PowangList(self.data + list.data)

    # ====== Number
    def multiplication_number(self, rhs: PowangNumber):
        return PowangList(self.data * int(rhs.data))
    
    def addition_number(self, rhs: PowangNumber):
        return PowangList(self.data + [rhs])

    # ====== String
    def addition_string(self, rhs: PowangString):
        return PowangList(self.data + [rhs])

# ====== STRUCT ========= TODO
class PowangStruct(PowangType_Base):
    data: dict[str, 'PowangAny']
    methods: dict[str, 'PowangCallable']
    type: Literal['struct'] = 'struct'
    def __init__(self, data: dict[str, 'PowangAny'], methods: dict[str, 'PowangCallable'] = {}, *,
        const: bool = False
    ):
        super().__init__(data, const=const)
        self.methods = methods
        
    def has(self, name: str):
        return False # not implemented

# ====== NOV =========
class PowangNov(PowangType_Base):
    data: None
    type: Literal['nov'] = 'nov'
    def __init__(self):
        super().__init__(None)

    def has(self, name: str):
        return False # not implemented

# ====== ANY =========
PowangAny = Union[
    PowangNov,
    PowangNumber,
    PowangString,
    PowangList,
    PowangStruct,
]

# ====== ERROR =========
class PowangError(PowangType_Base):
    data: tuple[str, str, list[str]]
    type: Literal['error'] = 'error'
    def __init__(self, data: tuple[str, str, list[str]]):
        super().__init__(data, const=True)
        
# ====== CALLABLE =========
class PowangCallable:
    def __init__(self, min_argc: int, max_argc: int, is_flex: bool, function: Callable[(...), PowangAny | PowangError]):
        self.min_argc = min_argc
        self.max_argc = max_argc
        self.is_flex = is_flex
        self.function = function
        
def deduce_polang_type(x, *, const: bool = False):
    if isinstance(x, (int, float)):
        return PowangNumber(x, const=const)
    elif isinstance(x, str):
        return PowangString(x, const=const)
    elif isinstance(x, list):
        return PowangList(x, const=const)
    elif isinstance(x, object):
        return PowangStruct(x.__dict__, const=const)
    elif isinstance(x, BaseException):
        return PowangError(x.args)
    elif x is None:
        return PowangNov()