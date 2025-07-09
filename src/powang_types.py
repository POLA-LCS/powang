from typing import Union, Literal, Any, Callable, Optional
from dataclasses import dataclass
from .lexer.token import DictRepr
from .error import *

class PowangTypeBase:
    @dataclass
    class PropertyConst:
        it_is     : bool = False
        can_change : bool = False

        def __bool__(self) -> bool:
            return self.it_is

    @dataclass
    class PropertyWeak:
        it_is    : bool = False
        has_value : bool = True

        def __bool__(self) -> bool:
            return self.it_is
  
    PropertiesDict = dict[str, bool | PropertyConst | PropertyWeak | str | None]
  
    data      : Any  = None
    type      : Any  = None
    type_name : str  = ''
    defined   : bool = True
    some      : str  = ''
    const     : PropertyConst
    weak      : PropertyWeak
    sizeable  : bool = False
    indexable : bool = False
    
    def __init__(self, data):
        self.data    = data
        self.defined = True

        self.const = self.PropertyConst()
        self.weak  = self.PropertyWeak()
        self.type_name = self.type

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
    def cast(right: 'PowangAny') -> Optional['PowangAny']:
        return None

    def size(self) -> Optional['PowangInteger']:
        raise powang_throw(powang_error_unsupported_operation(None, self.type, 'size'))

    def index(self, index: 'PowangAny') -> 'PowangAny':
        raise powang_throw(powang_error_unsupported_operation(None, self.type, 'index'))

    def iterate(self) -> 'PowangArray':
        raise powang_throw(powang_error_unsupported_operation(None, self.type, 'iterate'))

    def __add__(self, right: 'PowangAny') -> Optional['PowangAny']:
        return None
    
    def __sub__(self, right: 'PowangAny') -> Optional['PowangAny']:
        return None
    
    def __mul__(self, right: 'PowangAny') -> Optional['PowangAny']:
        return None
    
    def __truediv__(self, right: 'PowangAny') -> Optional['PowangAny']:
        return None

    def __eq__(self, value: 'PowangAny') -> bool: # type: ignore
        return self.data == value.data

    def __lt__(self, value: 'PowangAny') -> bool:
        return self.data < value.data

    def __gt__(self, value: 'PowangAny') -> bool:
        return self.data > value.data

    def __repr__(self):
        return f'PowangType({self.type} | {', '.join([key for key, value in self.properties.items() if value])}: {self.data})'
    
# ====== NOVA =========
class PowangNova(PowangTypeBase):
    data: None
    type: Literal['nova'] = 'nova'
    def __init__(self, _: None = None):
        super().__init__(None)
        self.weak = PowangTypeBase.PropertyWeak(True, False)

    @staticmethod
    def cast(right: 'PowangAny'):
        if right.type == PowangNova.type:
            return right
        return None
    
# ====== SOME =========
class PowangSome(PowangTypeBase):
    data: Any
    type: Literal['some'] = 'some'
    def __init__(self, data: Any = 0):
        super().__init__(data)
        self.some = 'nova'

    @staticmethod
    def cast(right: 'PowangAny'):
        return PowangCopyConstruct(right)

# ====== BOOL =========
class PowangBoolean(PowangTypeBase):
    data: bool
    type: Literal['boolean'] = 'boolean'
    def __init__(self, data: bool = False):
        super().__init__(data)
        
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
        #     result.data = False
        # elif right.type == PowangObjectType.type:
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
class PowangInteger(PowangTypeBase):
    data: int
    type: Literal['integer'] = 'integer'
    def __init__(self, data: int = 0):
        super().__init__(data)

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
        return None

    def __sub__(self, right: 'PowangAny'):
        if right.type == PowangInteger.type:
            return PowangInteger(self.data - right.data)
        if right.type == PowangBoolean.type:
            return PowangBoolean.cast(self) - right
        return None

    def __mul__(self, right: 'PowangAny'):
        if right.type == PowangInteger.type:
            return PowangInteger(self.data * right.data)
        if right.type == PowangBoolean.type:
            return PowangBoolean.cast(self) * right
        if right.type == PowangString.type:
            return PowangString(right.data * self.data)
        if right.type == PowangArray.type:
            return PowangArray(right.data * self.data)
        return None

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
        return None

class PowangNumber(PowangTypeBase):
    data: float
    type: Literal['number'] = 'number'
    def __init__(self, data: float = 0.0):
        super().__init__(data)

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
        return None

    def __sub__(self, right: 'PowangAny'):
        if right.type == PowangNumber.type:
            return PowangNumber(self.data - right.data)
        if right.type == PowangBoolean.type:
            return PowangBoolean.cast(self) - right
        return None

    def __mul__(self, right: 'PowangAny'):
        if right.type == PowangNumber.type:
            return PowangNumber(self.data * right.data)
        if right.type == PowangBoolean.type:
            return PowangBoolean.cast(self) * right
        return None

    def __truediv__(self, right: 'PowangAny'):
        if right.type == PowangNumber.type:
            if right.data == 0.0:
                return PowangNova()
            return PowangNumber(self.data / right.data)
        if right.type == PowangBoolean.type:
            return PowangBoolean.cast(self) / right
        return None

# ====== STRING =========
class PowangString(PowangTypeBase):
    data: str
    type: Literal['string'] = 'string'
    def __init__(self, data: str = ''):
        super().__init__(data)

    @staticmethod
    def cast(right: 'PowangAny'):
        if right.type == PowangString.type:
            return PowangString(right.data)
        return None

    def size(self) -> 'PowangInteger':
        return PowangInteger(len(self.data))

    def index(self, index: 'PowangAny') -> 'PowangString':
        assert index.type == PowangInteger.type, powang_error_type_match(f'{PowangArray.type} indexing', PowangInteger.type, index.type)
        assert 0 <= index.data < (size := self.size().data), powang_error_index_out_of_range(index.data, size)
        return PowangString(self.data[index.data])

    def iterate(self) -> 'PowangArray':
        return PowangArray([PowangString(char) for char in self.data])

    def __add__(self, right: 'PowangAny'):
        if right.type == PowangString.type:
            return PowangString(self.data + right.data)
        if right.type == PowangBoolean.type:
            return PowangBoolean.cast(self) + right
        return None

    def __sub__(self, right: 'PowangAny'):
        if right.type == PowangString.type:
            return PowangString(self.data.replace(right.data, '', 1))
        if right.type == PowangBoolean.type:
            return PowangBoolean.cast(self) - right
        return None

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
        return None
    
# ====== ARRAY =========
class PowangArray(PowangTypeBase):
    data: list['PowangAny']
    type: Literal['array'] = 'array'
    def __init__(self, data: list['PowangAny'] = []):
        super().__init__(data)

    @staticmethod        
    def cast(right: 'PowangAny'):
        if right.type == PowangArray.type:
            return PowangArray(right.data)
        if right.type == PowangMap.type:
            return PowangArray([PowangArray([key, value]) for key, value in right.data.items()])
        return None

    def size(self) -> 'PowangInteger':
        return PowangInteger(len(self.data))
    
    def index(self, index: 'PowangAny') -> 'PowangAny':
        assert index.type == PowangInteger.type, powang_error_type_match(f'{PowangArray.type} indexing', PowangInteger.type, index.type)
        assert 0 <= index.data < (size := self.size().data), powang_error_index_out_of_range(index.data, size)
        return self.data[index.data]
    
    def iterate(self) -> 'PowangArray':
        return PowangArray(self.data)

    def __add__(self, right: 'PowangAny'):
        if right.type == PowangArray.type:
            return PowangArray(self.data + right.data)
        if right.type == PowangBoolean.type:
            return PowangBoolean.cast(self) + right
        return None

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
        return None

    def __mul__(self, right: 'PowangAny'):
        if right.type == PowangBoolean.type:
            return PowangBoolean.cast(self) * right
        if right.type == PowangInteger.type:
            return right * self
        return None

    def __truediv__(self, right: 'PowangAny'):
        if right.type == PowangBoolean.type:
            return PowangBoolean.cast(self) / right
        return None
    
# ====== MAP =========
class PowangMap(PowangTypeBase):
    data: dict['PowangAny', 'PowangAny']
    type: Literal['map'] = 'map'
    def __init__(self, data: dict['PowangAny', 'PowangAny'] = {}):
        super().__init__(data)
        self.sizeable = True
        self.indexable = True

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

    def size(self) -> PowangInteger:
        return PowangInteger(len(self.data))
    
    def index(self, index: 'PowangAny') -> 'PowangAny':
        assert (value := self.data.get(index)) is not None, powang_error_key(str(index))
        return value

    def iterate(self) -> 'PowangArray':
        return PowangArray([PowangArray([key, value]) for key, value in self.data.items()])

    def __add__(self, right: 'PowangAny') -> Optional['PowangAny']:
        if right.type == PowangMap.type:
            new_map = PowangMap(self.data)
            for key, value in right.data.items():
                new_map.data[key] = value
            return new_map
        return None
    
# ====== USER DEFINED FUNCTION ========= TODO
class PowangFunction(PowangTypeBase):
    data: list[DictRepr]
    type: Literal['function'] = 'function'
    def __init__(self,
        args: list[DictRepr],
        data: list[DictRepr],
        return_expr: DictRepr
    ):
        super().__init__(data)
        self.args = args
        self.return_expr = return_expr
        self.min_argc = len(self.args)
        
    def __repr__(self) -> str:
        return f"({', '.join(f"{arg['value']['identifier']['value']}: {arg}" for arg in self.args)}): {self.return_expr['value']}"

# ====== USER TYPES =========
CONSTRUCTOR_METHOD_NAME: Literal['constructor'] = 'constructor'

class PowangObjectType(PowangTypeBase): # user defined types
    type_name: str = 'object'
    data: dict[str, 'PowangAny'] = {}  # public props
    type: Literal['type'] = 'type'
 
    private_props  : dict[str, 'PowangAny']
    public_meths : dict[str, list[PowangFunction]]
    private_meths: dict[str, list[PowangFunction]]
    def __init__(self,
        public_props : dict[str, 'PowangAny']          = {},
        private_props: dict[str, 'PowangAny']          = {},
        public_meths : dict[str, list[PowangFunction]] = {},
        private_meths: dict[str, list[PowangFunction]] = {},
    ):
        super().__init__(public_props)
        self.private_props = private_props
        self.public_meths = public_meths
        self.private_meths = private_meths

    def getConstructors(self) -> list[PowangFunction]:
        assert (constructors := self.getMethods(CONSTRUCTOR_METHOD_NAME, False)) is not None, powang_error_development(
            'method call', 'Constructor not founded', [
                "Somehow the type has no constructors..."
            ]
        )
        return constructors

    def getMethods(self, method_name: str, private: bool) -> Optional[list[PowangFunction]]:
        public_methods = self.public_meths.get(method_name)
        if private and (match_methods := self.private_meths.get(method_name)) is not None:
            return match_methods + public_methods if public_methods is not None else []
        return public_methods

    def getProperty(self, property_name: str, private: bool) -> Optional['PowangAny']:
        if private and (match_property := self.private_props.get(property_name)) is not None:
            return match_property
        return self.data.get(property_name)

from typing import TextIO
class PowangFileStream(PowangTypeBase):
    data: str
    type: Literal['file'] = 'file'

    def __init__(self, data: PowangString, mode: PowangString):
        super().__init__(data)
        self.mode = mode
        self.text_io: Optional[TextIO] = None

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
    PowangFunction,  # FunctionType
    PowangObjectType,  # object
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
        PowangMap.type       : PowangMap,
        PowangFunction.type  : PowangFunction,
        PowangObjectType.type  : PowangObjectType,
    }[type]

def PowangCopyConstruct(any: PowangAny) -> PowangAny:
    if any.type == PowangObjectType.type:
        return PowangCopyConstructObjectType(any)
    value = PowangTypeMap(any.type)(any.data)
    value.weak = any.weak
    value.const = any.const
    return value

def PowangCopyConstructObjectType(anyType: PowangObjectType) -> PowangObjectType:
    value = PowangObjectType(
        anyType.data,
        anyType.private_props,
        anyType.public_meths,
        anyType.private_meths,
    )
    value.type_name = anyType.type_name
    value.weak = anyType.weak
    value.const = anyType.const
    return value

def PowangTypeCast(type: str, any: PowangAny) -> PowangAny | None:
    return PowangTypeMap(type).cast(any) # type: ignore