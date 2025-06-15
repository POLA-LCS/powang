from typing import Union, Literal, Any

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
        
    def copy(self):
        return PowangType_Base(self.data, const=self.const)

    def __repr__(self):
        return f'PowangType({self.type} {'const' if self.const else 'mutable'}: {self.data})'

# ====== NOV =========
class PowangNov(PowangType_Base):
    data: None
    type: Literal['nov'] = 'nov'
    def __init__(self):
        super().__init__(None)

    def equal_nov(self, _: 'PowangNov'):
        return True

# ====== BOOL =========
class PowangBool(PowangType_Base):
    state: bool
    type: Literal['bool'] = 'bool'
    def __init__(self, state: bool, *,
        const: bool = False
    ):
        assert isinstance(state, bool), error_logic(
            "I'm sorry, development error :(", [
                f"Somehow a {type(state)} is trying to construct a PowangBoolean",
                "but only accepts float types"
        ])
        super().__init__(state, const=const)
        self.state = state

    @property
    def data(self):
        return 'true' if self.state else 'false'

    @data.setter
    def data(self, state: bool):
        self.state = state

# ====== NUMBER =========
class PowangNumber(PowangType_Base):
    data: float
    type: Literal['number'] = 'number'
    def __init__(self, data: float, *,
        const: bool = False
    ):
        super().__init__(data, const=const)
        
    # ====== Number =========
    def addition_number(self, rhs: 'PowangNumber'):
        return PowangNumber(self.data + rhs.data)

    def substraction_number(self, rhs: 'PowangNumber'):
        return PowangNumber(self.data - rhs.data)

    def multiplication_number(self, rhs: 'PowangNumber'):
        return PowangNumber(self.data * rhs.data)

    def division_number(self, rhs: 'PowangNumber'):
        return PowangNumber(self.data / rhs.data)

    # ====== String =========
    def addition_string(self, rhs: 'PowangString'):
        return PowangNumber(self.data + len(rhs.data))

    def substraction_string(self, rhs: 'PowangString'):
        """LEFT HAND SIDE"""
        return PowangString(rhs.data[self.data:])

    def multiplication_string(self, rhs: 'PowangString'):
        return rhs.multiplication_number(self)
    
    def division_string(self, rhs: 'PowangString'):
        return PowangList([PowangString(rhs.data[part:part + int(self.data)]) for part in range(0, len(rhs.data), int(self.data))])

    # ====== List =========
    def addition_list(self, rhs: 'PowangString'):
        return PowangNumber(self.data + len(rhs.data))
    
    def substraction_list(self, rhs: 'PowangList'):
        """LEFT HAND SIDE"""
        return PowangList(rhs.data[self.data:])

    def multiplication_list(self, rhs: 'PowangList'):
        return rhs.multiplication_number(self)
    
    def division_list(self, rhs: 'PowangList'):
        return PowangList([PowangList(rhs.data[part:part + int(self.data)]) for part in range(0, len(rhs.data), int(self.data))])
    
# ====== STRING =========
class PowangString(PowangType_Base):
    data: str
    type: Literal['string'] = 'string'
    def __init__(self, data: str, *,
        const: bool = False
    ):
        super().__init__(data, const=const)

    # ====== String =========
    def addition_string(self, rhs: 'PowangString'):
        return PowangString(self.data + rhs.data)

    def substraction_string(self, rhs: 'PowangString'):
        return PowangString(self.data.replace(rhs.data, '', 1))

    def multiplication_string(self, rhs: 'PowangString'):
        return PowangNumber(self.data.count(rhs.data))

    def division_string(self, rhs: 'PowangString'):
        return PowangList([PowangString(part) for part in self.data.split(rhs.data)])
    
    # ====== Number =========
    def addition_number(self, rhs: PowangNumber):
        return self.addition_string(PowangString(str(rhs.data)))
    
    def substraction_number(self, rhs: PowangNumber):
        return PowangString(self.data[:-int(rhs.data)])
    
    def multiplication_number(self, rhs: PowangNumber):
        return PowangString(self.data * int(rhs.data))

    def division_number(self, rhs: PowangNumber):
        return PowangList([PowangString(self.data[i - int(rhs.data):i]) for i in range(len(self.data), 0, -int(rhs.data))])

# ====== LIST =========
class PowangList(PowangType_Base):
    data: list['PowangAny']
    type: Literal['list'] = 'list'
    def __init__(self, data: list['PowangAny'], *,
        const: bool = False
    ):
        super().__init__(data, const=const)
        
    # ====== List
    def addition_list(self, list: 'PowangList'):
        return PowangList(self.data + list.data)

    # ====== Number
    def addition_number(self, rhs: PowangNumber):
        return PowangList(self.data + [rhs])
    
    def multiplication_number(self, rhs: PowangNumber):
        return PowangList(self.data * int(rhs.data))

    def division_number(self, rhs: PowangNumber):
        return PowangList(self.data[::int(rhs.data)])

    # ====== String
    def addition_string(self, rhs: PowangString):
        return PowangList(self.data + [rhs])

# ====== USER DEFINED FUNCTION ========= TODO
class PowangFunction(PowangType_Base):
    data: list[str]
    type: Literal['function'] = 'function'
    def __init__(self,
        min_argc: int = 0,
        max_argc: int = 0,
        data: list[str] = []
    ):
        super().__init__(data, const=True)
        self.min_argc = min_argc
        self.max_argc = max_argc

# ====== STRUCT ========= TODO
class PowangStruct(PowangType_Base):   # user defined types
    data: dict[str, 'PowangAny']       # properties
    methods: dict[str, PowangFunction] = { # methods
        'bool': PowangFunction(0, 0, [
            '+ 0'
        ])
    }
    type: Literal['struct'] = 'struct'
    def __init__(self, data: dict[str, 'PowangAny'], methods: dict[str, PowangFunction] = {}, *,
        const: bool = False
    ):
        super().__init__(data, const=const)
        self.methods = methods
        
    def has(self, name: str):
        if self.methods.get(name) is not None:
            return True
        return False

# ====== ANY =========
PowangAny = Union[
    PowangNov,
    PowangNumber,
    PowangBool,
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

def PowangCopyConstruct(any: PowangAny) -> PowangAny:
    return {
        PowangNov.type   : PowangNov,
        PowangNumber.type: PowangNumber,
        PowangBool.type  : PowangBool,
        PowangString.type: PowangString,
        PowangList.type  : PowangList,
        PowangStruct.type: PowangStruct,
    }[any.type](any.data, const=any.const)