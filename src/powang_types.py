from typing import Union, Literal, Any, Callable, Optional
from abc import abstractmethod


class PowangType_Base:
    type: Any = None

    def __init__(self, data, *, properties: dict[str, bool] = {}):
        self.data = data
        self.defined = True
        self.const   = False
        self.weak    = False
        self.nova    = False
        self.some    = False
        
        for prop, value in properties.items():
            self.__setattr__(prop, value)

    def setprop(self, prop: str, value: bool):
        self.__setattr__(prop, value)
        return self

    @property
    def properties(self):
        return {
            'defined': self.defined,
            'const'  : self.const,
            'weak'   : self.weak,
            'nova'   : self.nova,
            'some'   : self.some,
        }

    @staticmethod
    def cast(right: 'PowangAny') -> Optional['PowangAny']: # type: ignore
        return None

    def __add__(self, right: 'PowangAny') -> 'PowangAny': # type: ignore
        return PowangNova()
    
    def __sub__(self, right: 'PowangAny') -> 'PowangAny': # type: ignore
        return PowangNova()
    
    def __mul__(self, right: 'PowangAny') -> 'PowangAny': # type: ignore
        return PowangNova()
    
    def __truediv__(self, right: 'PowangAny') -> 'PowangAny': # type: ignore
        return PowangNova()

    def __eq__(self, value: object) -> bool:
        return self.data == value.data # type: ignore

    def __repr__(self):
        return f'PowangType({self.type} {[key for key, value in self.properties.items() if value]}: {self.data})'
    
# ====== NOVA =========
class PowangNova(PowangType_Base):
    data: None
    type: Literal['nova'] = 'nova'
    def __init__(self, _: None = None, *, properties: dict[str, bool] = {}):
        super().__init__(None, properties=properties)
        self.nova = True
    
# ====== SOME =========
class PowangSome(PowangType_Base):
    data: Any
    type: Literal['some'] = 'some'
    def __init__(self, data: Any = 0, *, properties: dict[str, bool] = {}):
        super().__init__(data, properties=properties)
        self.some = True

    @staticmethod
    def cast(right: 'PowangAny'):
        return PowangCopyConstruct(right)

# ====== BOOL =========
class PowangBoolean(PowangType_Base):
    data: bool
    type: Literal['boolean'] = 'boolean'
    def __init__(self, data: bool = False, *, properties: dict[str, bool] = {}):
        super().__init__(data, properties=properties)
        
    @staticmethod
    def cast(right: 'PowangAny'):
        result = PowangBoolean(False)
        if right.type == PowangBoolean.type:
            result.data = right.data
        elif right.type == PowangInteger.type:
            result.data = right.data != 0
        elif right.type == PowangNumber.type:
            result.data = right.data != 0.0
        elif right.type == PowangString.type or right.type == PowangContainer.type:
            result.data = len(right.data) > 0
        # elif right.type == PowangNova.type:
        #     return False
        # elif right.type == PowangUserType.type:
        #     result.data = right.methods['boolean']().data # type: ignore
        return result

    def __add__(self, right: 'PowangAny'):
        return PowangBoolean(self.data or self.cast(right).data)

    def __sub__(self, right: 'PowangAny'):
        return PowangBoolean(self.data or not self.cast(right).data)

    def __mul__(self, right: 'PowangAny'):
        return PowangBoolean(self.data and self.cast(right).data)

    def __truediv__(self, right: 'PowangAny'):
        return PowangBoolean(self.data and not self.cast(right).data)

# ====== INTEGER =========
class PowangInteger(PowangType_Base):
    data: int
    type: Literal['integer'] = 'integer'
    def __init__(self, data: int = 0, *, properties: dict[str, bool] = {}):
        super().__init__(data, properties=properties)

    @staticmethod
    def cast(right: 'PowangAny'):
        if right.type == PowangInteger.type:
            return PowangInteger(right.data)
        if right.type == PowangBoolean.type:
            return PowangInteger(1 if right.data else 0)
        if right.type == PowangNumber.type:
            return PowangInteger(int(right.data))
        return None

    def __add__(self, right: 'PowangAny'):
        if right.type == PowangInteger.type:
            return PowangInteger(self.data + right.data)
        if right.type == PowangBoolean.type:
            return PowangBoolean.cast(self) + right
        return PowangNova()

    def __sub__(self, right: 'PowangAny'):
        if right.type == PowangInteger.type:
            return PowangInteger(self.data - right.data)
        if right.type == PowangBoolean.type:
            return PowangBoolean.cast(self) - right
        return PowangNova()

    def __mul__(self, right: 'PowangAny'):
        if right.type == PowangInteger.type:
            return PowangInteger(self.data * right.data)
        if right.type == PowangBoolean.type:
            return PowangBoolean.cast(self) * right
        if right.type == PowangString.type:
            return PowangString(right.data * self.data)
        if right.type == PowangContainer.type:
            return PowangContainer(right.data * self.data)
        return PowangNova()

    def __truediv__(self, right: 'PowangAny'):
        if right.type == PowangBoolean.type:
            return PowangBoolean.cast(self) / right
        if right.type == PowangNumber.type:
            if right.data == 0.0:
                return PowangNova()
            return PowangInteger(int(self.data / right.data))
        if right.type == PowangInteger.type:
            if right.data == 0:
                return PowangNova()
            return PowangInteger(self.data // right.data)
        if right.type == PowangString.type:
            return PowangContainer([PowangString(right.data[i:i + self.data]) for i in range(0, len(right.data), self.data)])
        if right.type == PowangContainer.type:
            return PowangContainer([PowangContainer([element for element in right.data[i:i + self.data]]) for i in range(0, len(right.data), self.data)])
        return PowangNova()

class PowangNumber(PowangType_Base):
    data: float
    type: Literal['number'] = 'number'
    def __init__(self, data: float = 0.0, *,properties: dict[str, bool] = {}):
        super().__init__(data, properties=properties)

    def get_number(self):
        """returns an int if its possible, else returns a float"""
        return int(self.data) if self.data.is_integer() else self.data

    @staticmethod
    def cast(right: 'PowangAny'):
        if right.type == PowangNumber.type:
            return PowangNumber(right.data)
        if right.type == PowangBoolean.type:
            return PowangNumber(1.0 if right.data else 0.0)
        if right.type == PowangInteger.type:
            return PowangNumber(float(right.data))
        return None

    def __add__(self, right: 'PowangAny'):
        if right.type == PowangNumber.type:
            return PowangNumber(self.data + right.data)
        if right.type == PowangBoolean.type:
            return PowangBoolean.cast(self) + right
        return PowangNova()

    def __sub__(self, right: 'PowangAny'):
        if right.type == PowangNumber.type:
            return PowangNumber(self.data - right.data)
        if right.type == PowangBoolean.type:
            return PowangBoolean.cast(self) - right
        return PowangNova()

    def __mul__(self, right: 'PowangAny'):
        if right.type == PowangNumber.type:
            return PowangNumber(self.data * right.data)
        if right.type == PowangBoolean.type:
            return PowangBoolean.cast(self) * right
        return PowangNova()

    def __truediv__(self, right: 'PowangAny'):
        if right.type == PowangNumber.type:
            if right.data == 0.0:
                return PowangNova()
            return PowangNumber(self.data / right.data)
        if right.type == PowangBoolean.type:
            return PowangBoolean.cast(self) / right
        return PowangNova()

# ====== STRING =========
class PowangString(PowangType_Base):
    data: str
    type: Literal['string'] = 'string'
    def __init__(self, data: str = '', *, properties: dict[str, bool] = {}):
        super().__init__(data, properties=properties)

    def __add__(self, right: 'PowangAny'):
        if right.type == PowangString.type:
            return PowangString(self.data + right.data)
        if right.type == PowangBoolean.type:
            return PowangBoolean.cast(self) + right
        return PowangNova()

    def __sub__(self, right: 'PowangAny'):
        if right.type == PowangString.type:
            return PowangString(self.data.replace(right.data, '', 1))
        if right.type == PowangBoolean.type:
            return PowangBoolean.cast(self) - right
        return PowangNova()

    def __mul__(self, right: 'PowangAny'):
        if right.type == PowangString.type:
            return PowangInteger(self.data.count(right.data))
        if right.type == PowangBoolean.type:
            return PowangBoolean.cast(self) * right
        return right * self

    def __truediv__(self, right: 'PowangAny'):
        if right.type == PowangString.type:
            return PowangContainer([PowangString(part) for part in self.data.split(right.data)])
        if right.type == PowangBoolean.type:
            return PowangBoolean.cast(self) / right
        if right.type == PowangInteger.type:
            return PowangContainer([PowangString(string.data[::-1]) for string in (right / PowangString(self.data[::-1])).data][::-1]) # type: ignore
        return PowangNova()
    
# ====== CONTAINER =========
class PowangContainer(PowangType_Base):
    data: list['PowangAny']
    type: Literal['container'] = 'container'
    def __init__(self, data: list['PowangAny'] = [], *, properties: dict[str, bool] = {}):
        super().__init__(data, properties=properties)
        
    @staticmethod
    def from_string(string: str) -> 'PowangContainer':
        return PowangContainer([PowangString(ch) for ch in string])

    def __add__(self, right: 'PowangAny'):
        if right.type == PowangContainer.type:
            return PowangContainer(self.data + right.data)
        if right.type == PowangBoolean.type:
            return PowangBoolean.cast(self) + right
        return PowangNova()

    def __sub__(self, right: 'PowangAny'):
        if right.type == PowangBoolean.type:
            return PowangBoolean.cast(self) - right
        if right.type == PowangInteger.type:
            return PowangContainer(self.data[:-right.data])
        if right.type == PowangContainer.type:
            result = PowangContainer([element for element in right.data])
            assert result.type == PowangContainer.type, ...
            for element in right.data:
                while element in result.data:
                    result.data.remove(element)
            return result
        return PowangNova()

    def __mul__(self, right: 'PowangAny'):
        if right.type == PowangBoolean.type:
            return PowangBoolean.cast(self) * right
        if right.type == PowangInteger.type:
            return right * self
        return PowangNova()

    def __truediv__(self, right: 'PowangAny'):
        if right.type == PowangBoolean.type:
            return PowangBoolean.cast(self) / right
        return PowangNova()

# ====== USER DEFINED FUNCTION ========= TODO
class PowangFunction(PowangType_Base):
    data: list[str]
    type: Literal['function'] = 'function'
    def __init__(self,
        min_argc: int = 0,
        max_argc: int = 0,
        data: list[str] = []
    ):
        super().__init__(data, properties={'const': True})
        self.min_argc = min_argc
        self.max_argc = max_argc
        
# ====== STRUCT ========= TODO
class PowangUserType(PowangType_Base):      # user defined types
    name: str
    data: dict[str, 'PowangAny']            # properties
    methods: dict[str, PowangFunction] = {} # methods
    
    type: Literal['type'] = 'type'
    def __init__(self,
        name: str,
        data: dict[str, 'PowangAny'],
        methods: dict[str, PowangFunction] = {}, *,
        properties: dict[str, bool] = {}
    ):
        super().__init__(data, properties=properties)
        self.methods = methods
        self.name = name

# ====== ANY =========
PowangAny = Union[
    PowangNova,     # None
    PowangSome,     # Any
    PowangBoolean,  # bool
    PowangInteger,  # int
    PowangNumber,   # float
    PowangString,   # str
    PowangContainer,     # list
    PowangUserType, # object
]

# ====== ERROR =========
class PowangError(PowangType_Base):
    data: tuple[str, str, list[str]]
    type: Literal['error'] = 'error'
    def __init__(self, data: tuple[str, str, list[str]]):
        super().__init__(data, properties={'const': True})

def PowangTypeMap(type: str) -> Callable[(...), PowangAny]:
    return {
        PowangNova.type     : PowangNova,
        PowangSome.type     : PowangSome,
        PowangInteger.type  : PowangInteger,
        PowangNumber.type   : PowangNumber,
        PowangBoolean.type     : PowangBoolean,
        PowangString.type   : PowangString,
        PowangContainer.type     : PowangContainer,
        PowangUserType.type : PowangUserType,
    }[type]

def PowangCopyConstruct(any: PowangAny) -> PowangAny:
    return PowangTypeMap(any.type)(any.data, properties=any.properties)

def PowangCast(type: str, any: PowangAny) -> PowangAny | None:
    return PowangTypeMap(type).cast(any) # type: ignore