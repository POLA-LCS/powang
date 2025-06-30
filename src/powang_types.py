from typing import Union, Literal, Any, Callable, Optional
from dataclasses import dataclass
from .error import *


class PowangType_Base:
    @dataclass
    class PropertyConst:
        _it_is     : bool = False
        can_change : bool = False

        def __bool__(self) -> bool:
            return self._it_is

    @dataclass
    class PropertyWeak:
        _it_is    : bool = False
        has_value : bool = True

        def __bool__(self) -> bool:
            return self._it_is
  
    PropertiesDict = dict[str, bool | PropertyConst | PropertyWeak | str | None]
  
    data    : Any           = None
    type    : Any           = None
    defined : bool          = True
    some    : str | None    = None
    const   : PropertyConst
    weak    : PropertyWeak
    
    def __init__(self, data, *, properties: PropertiesDict = {}
    ):
        self.data = data
        self.defined    = True

        self.const = self.PropertyConst()
        self.weak  = self.PropertyWeak()

        for prop, value in properties.items():
            self.__setattr__(prop, value)

    @property
    def properties(self):
        return {
            'defined'     : self.defined,
            'const'       : self.const,
            'weak'        : self.weak,
            'some'        : self.some,
        }
        
    def __hash__(self) -> int:
        return hash(self.data)

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

    def __eq__(self, value: 'PowangAny') -> bool: # type: ignore
        return self.data == value.data

    def __repr__(self):
        return f'PowangType({self.type} | {', '.join([key for key, value in self.properties.items() if value])}: {self.data})'
    
# ====== NOVA =========
class PowangNova(PowangType_Base):
    data: None
    type: Literal['nova'] = 'nova'
    def __init__(self, _: None = None, *, properties: PowangType_Base.PropertiesDict = {}):
        super().__init__(None, properties=properties)
        self.weak.has_value = False

    @staticmethod
    def cast(right: 'PowangAny'):
        if right.type == PowangNova.type:
            return right
        return None
    
# ====== SOME =========
class PowangSome(PowangType_Base):
    data: Any
    type: Literal['some'] = 'some'
    def __init__(self, data: Any = 0, *, properties: PowangType_Base.PropertiesDict = {}):
        super().__init__(data, properties=properties)
        self.some = 'some'

    @staticmethod
    def cast(right: 'PowangAny'):
        return PowangCopyConstruct(right)

# ====== BOOL =========
class PowangBoolean(PowangType_Base):
    data: bool
    type: Literal['boolean'] = 'boolean'
    def __init__(self, data: bool = False, *, properties: PowangType_Base.PropertiesDict = {}):
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
        elif right.type == PowangString.type or right.type == PowangArray.type:
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
    def __init__(self, data: int = 0, *, properties: PowangType_Base.PropertiesDict = {}):
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
        if right.type == PowangArray.type:
            return PowangArray(right.data * self.data)
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
            return PowangArray([PowangString(right.data[i:i + self.data]) for i in range(0, len(right.data), self.data)])
        if right.type == PowangArray.type:
            return PowangArray([PowangArray([element for element in right.data[i:i + self.data]]) for i in range(0, len(right.data), self.data)])
        return PowangNova()

class PowangNumber(PowangType_Base):
    data: float
    type: Literal['number'] = 'number'
    def __init__(self, data: float = 0.0, *, properties: PowangType_Base.PropertiesDict = {}):
        super().__init__(data, properties=properties)

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
    def __init__(self, data: str = '', *, properties: PowangType_Base.PropertiesDict = {}):
        super().__init__(data, properties=properties)

    @staticmethod
    def cast(right: 'PowangAny'):
        if right.type == PowangString.type:
            return PowangString(right.data)
        return None

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
            return PowangArray([PowangString(part) for part in self.data.split(right.data)])
        if right.type == PowangBoolean.type:
            return PowangBoolean.cast(self) / right
        if right.type == PowangInteger.type:
            return PowangArray([PowangString(string.data[::-1]) for string in (right / PowangString(self.data[::-1])).data][::-1]) # type: ignore
        return PowangNova()
    
# ====== ARRAY =========
class PowangArray(PowangType_Base):
    data: list['PowangAny']
    type: Literal['array'] = 'array'
    def __init__(self, data: list['PowangAny'] = [], *, properties: PowangType_Base.PropertiesDict = {}):
        super().__init__(data, properties=properties)

    @staticmethod        
    def cast(right: 'PowangAny'):
        if right.type == PowangArray.type:
            return PowangArray(right.data)
        if right.type == PowangMap.type:
            return PowangArray([PowangArray([key, value]) for key, value in right.data.items()])
        return None

    def __add__(self, right: 'PowangAny'):
        if right.type == PowangArray.type:
            return PowangArray(self.data + right.data)
        if right.type == PowangBoolean.type:
            return PowangBoolean.cast(self) + right
        return PowangNova()

    def __sub__(self, right: 'PowangAny'):
        if right.type == PowangBoolean.type:
            return PowangBoolean.cast(self) - right
        if right.type == PowangInteger.type:
            return PowangArray(self.data[:-right.data])
        if right.type == PowangArray.type:
            result = PowangArray([element for element in right.data])
            assert result.type == PowangArray.type, ...
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

# ====== MAP =========
class PowangMap(PowangType_Base):
    data: dict['PowangAny', 'PowangAny']
    type: Literal['map'] = 'map'
    def __init__(self, data: dict['PowangAny', 'PowangAny'] = {}, *, properties: PowangType_Base.PropertiesDict = {}):
        super().__init__(data, properties=properties)

    @staticmethod
    def cast(right: 'PowangAny'):
        if right.type == PowangMap.type:
            return PowangMap(right.data)
        if right.type == PowangArray.type:
            new_map = PowangMap()
            for i, item in enumerate(right.data):
                assert item.type == PowangArray.type, powang_error_format("LOGIC", "array to map", "Invalid format", [
                    f"map items must be {PowangArray.type}",
                    f"but {item.type} was encounter"
                ])
                
                assert (length := len(item.data)) == 2, powang_error_format("LOGIC", "array to map", "Invalid format", [
                    f"map items must be {PowangArray.type} pairs of [key, value]",
                    f"but element {i + 1} is an {PowangArray.type} of {length} items"
                ])
                
                new_map.data[item.data[0]] = item.data[1]
            return new_map
        return None

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
        properties: PowangType_Base.PropertiesDict = {}
    ):
        super().__init__(data, properties=properties)
        self.methods = methods
        self.name = name

# ====== ANY =========
PowangAny = Union[
    PowangNova,      # None
    PowangSome,      # Any
    PowangBoolean,   # bool
    PowangInteger,   # int
    PowangNumber,    # float
    PowangString,    # str
    PowangArray,     # list
    PowangMap,       # dict
    PowangUserType,  # object
]

def PowangTypeMap(type: str) -> Callable[(...), PowangAny]:
    return {
        PowangNova.type      : PowangNova,
        PowangSome.type      : PowangSome,
        PowangInteger.type   : PowangInteger,
        PowangNumber.type    : PowangNumber,
        PowangBoolean.type   : PowangBoolean,
        PowangString.type    : PowangString,
        PowangArray.type     : PowangArray,
        PowangMap.type     : PowangMap,
        PowangUserType.type  : PowangUserType,
    }[type]

def PowangCopyConstruct(any: PowangAny) -> PowangAny:
    valor = PowangTypeMap(any.type)(any.data, properties=any.properties)
    return valor

def PowangCast(type: str, any: PowangAny) -> PowangAny | None:
    return PowangTypeMap(type).cast(any) # type: ignore