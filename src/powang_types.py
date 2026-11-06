from typing import Union, Literal, Any, Callable, Optional
from dataclasses import dataclass
from threading import Lock
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
    any       : str  = ''
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
            'any'        : self.any,
        }
        
    def __hash__(self) -> int:
        try:
            return hash(self.data)
        except TypeError:
            powang_throw(powang_error_format('KEY', None, "unhashable key", [
                f"value of type {self.type} cannot be used as a map key"
            ]))
            raise # unreachable, keeps type checkers happy

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

    def __mod__(self, right: 'PowangAny') -> Optional['PowangAny']:
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
class PowangAnyType(PowangTypeBase):
    data: Any
    type: Literal['any'] = 'any'
    def __init__(self, data: Any = 0):
        super().__init__(data)
        self.any = 'nova'

    @staticmethod
    def cast(right: 'PowangAny'):
        return PowangCopyConstruct(right)

# ====== BOOL =========
class PowangBoolean(PowangTypeBase):
    data: bool
    type: Literal['bool'] = 'bool'
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
        #     result.data = right.methods['bool']().data # type: ignore
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
    type: Literal['int'] = 'int'
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
        if right.type == PowangString.type or right.type == PowangArray.type:
            assert self.data > 0, powang_error_format('VALUE', f'{right.type} chunking', "Chunk size must be positive", [
                f"{right.type} cannot be divided into chunks of non-positive size {self.data}"
            ])
            if right.type == PowangString.type:
                return PowangArray([PowangString(right.data[i:i + self.data]) for i in range(0, len(right.data), self.data)])
            return PowangArray([PowangArray([element for element in right.data[i:i + self.data]]) for i in range(0, len(right.data), self.data)])
        return None

    def __mod__(self, right: 'PowangAny'):
        if right.type == PowangInteger.type:
            ## Division/modulo by zero yields nova instead of throwing.
            if right.data == 0:
                return PowangNova()
            return PowangInteger(self.data % right.data)
        return None

class PowangNumber(PowangTypeBase):
    data: float
    type: Literal['num'] = 'num'
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

    def __mod__(self, right: 'PowangAny'):
        if right.type == PowangNumber.type:
            ## Python's float modulo keeps the divisor's sign, matching Powang.
            if right.data == 0.0:
                return PowangNova()
            return PowangNumber(self.data % right.data)
        return None

# ====== STRING =========
class PowangString(PowangTypeBase):
    data: str
    type: Literal['str'] = 'str'
    def __init__(self, data: str = ''):
        super().__init__(data)

    @staticmethod
    def cast(right: 'PowangAny'):
        if right.type == PowangString.type:
            return PowangString(right.data)
        ## Error values print through their readable one-line form. This keeps
        ## `print(err)` useful without making errors JSON-serializable.
        if right.type == PowangErrorValue.type:
            return PowangString(right.data)
        ## Modules are opaque namespaces; their printable form names the module
        ## instead of exposing the exported member dictionary.
        if right.type == PowangModule.type:
            return PowangString(f'<module: {right.name}>')
        ## Tasks print as an opaque handle. The status is part of the surface
        ## so `print(t)` is useful without exposing thread internals.
        if right.type == PowangTask.type:
            return PowangString(repr(right))
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
    type: Literal['arr'] = 'arr'
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
            if right.data < 0:
                powang_throw(powang_error_format('VALUE', f'{self.type} subtraction', "Cannot remove a negative amount of elements", [
                    f"expected a non-negative {PowangInteger.type}, but {right.data} was encounter"
                ]))
            if right.data == 0:
                return PowangArray(list(self.data))
            return PowangArray(list(self.data[:-right.data]))
        if right.type == PowangArray.type:
            result = PowangArray(list(self.data))
            for element in right.data:
                if element in result.data:
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
    
# ====== TUPLE =========
class PowangTuple(PowangTypeBase):
    data: list['PowangAny']
    type: Literal['tup'] = 'tup'

    def __init__(self, data: Optional[list['PowangAny']] = None):
        super().__init__(list(data) if data is not None else [])

    def size(self) -> 'PowangInteger':
        return PowangInteger(len(self.data))

    def index(self, index: 'PowangAny') -> 'PowangAny':
        assert index.type == PowangInteger.type, powang_error_type_match(f'{PowangTuple.type} indexing', PowangInteger.type, index.type)
        assert 0 <= index.data < (size := self.size().data), powang_error_index_out_of_range(index.data, size)
        return self.data[index.data]

    def iterate(self) -> 'PowangArray':
        return PowangArray(self.data)

    def __add__(self, right: 'PowangAny') -> None:
        return None

    def __repr__(self) -> str:
        return '[' + ', '.join(repr(item) for item in self.data) + ']'


# ====== MAP =========
class PowangMap(PowangTypeBase):
    data: dict['PowangAny', 'PowangAny']
    type: Literal['map'] = 'map'
    def __init__(self, data: Optional[dict['PowangAny', 'PowangAny']] = None):
        super().__init__(dict(data) if data is not None else {})
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
        assert index in self.data, powang_error_key(str(index))
        return self.data[index]

    def iterate(self) -> 'PowangArray':
        return PowangArray([PowangArray([key, value]) for key, value in self.data.items()])

    def __add__(self, right: 'PowangAny') -> Optional['PowangAny']:
        if right.type == PowangMap.type:
            new_map = PowangMap(self.data)
            for key, value in right.data.items():
                new_map.data[key] = value
            return new_map
        return None
    
# ====== USER DEFINED FUNCTION =========
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
    data: dict[str, 'PowangAny']  # public props
    type: Literal['object'] = 'object'
    is_enum: bool = False
    is_enum: bool = False
 
    private_props  : dict[str, 'PowangAny']
    public_meths : dict[str, list[PowangFunction]]
    private_meths: dict[str, list[PowangFunction]]
    def __init__(self,
        public_props : Optional[dict[str, 'PowangAny']]          = None,
        private_props: Optional[dict[str, 'PowangAny']]          = None,
        public_meths : Optional[dict[str, list[PowangFunction]]] = None,
        private_meths: Optional[dict[str, list[PowangFunction]]] = None,
    ):
        super().__init__(dict(public_props) if public_props is not None else {})
        self.private_props = dict(private_props) if private_props is not None else {}
        self.public_meths = dict(public_meths) if public_meths is not None else {}
        self.private_meths = dict(private_meths) if private_meths is not None else {}

    def getConstructors(self) -> list[PowangFunction]:
        constructors = self.getMethods(CONSTRUCTOR_METHOD_NAME, False)
        if constructors is None:
            return []
        return constructors

    def getMethods(self, method_name: str, private: bool) -> Optional[list[PowangFunction]]:
        public_methods = self.public_meths.get(method_name)
        if private and (private_methods := self.private_meths.get(method_name)) is not None:
            return private_methods + (public_methods if public_methods is not None else [])
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

# ====== ERROR VALUE =========
class PowangErrorValue(PowangTypeBase):
    """A catchable language error exposed to Powang code.

    ``data`` holds a readable one-line form so existing printing paths keep
    working. ``error`` keeps the underlying ``PowangError`` for structured
    property access (kind, message, details, where, line, column, cause).
    """
    data: str
    type: Literal['error'] = 'error'

    def __init__(self, data: str = ''):
        super().__init__(data)
        self.error: Any = None

    @staticmethod
    def from_error(error: Any) -> 'PowangErrorValue':
        kind = getattr(error, 'kind', 'ERROR') or 'ERROR'
        message = getattr(error, 'message', '') or ''
        label = '[ERROR]' if kind == 'ERROR' else f'[{kind} ERROR]'
        readable = label + (f' {message}' if message else '')
        value = PowangErrorValue(readable)
        value.error = error
        return value

# ====== REFERENCE =========
class PowangReference(PowangTypeBase):
    """A temporary reference to a variable slot.

    References exist only for the duration of a call: `&name` creates one and a
    parameter declared `&type` receives it. The owner is the scope dictionary
    that holds the target binding, so reads and writes always see the live
    value even when the caller's scope keeps running.
    """

    type: Literal['reference'] = 'reference'

    def __init__(self, owner: dict[str, Any], name: str, target_type: str = 'any'):
        super().__init__(None)
        self.owner = owner
        self.name = name
        self.target_type = target_type
        self.defined = True

    def get(self) -> 'PowangAny':
        return self.owner[self.name]

    def set(self, value: 'PowangAny') -> None:
        self.owner[self.name] = value

    def __repr__(self) -> str:
        return f"<reference: {self.name}>"


class PowangElementReference(PowangTypeBase):
    """A reference to one element of an array-like container."""

    type: Literal['reference'] = 'reference'

    def __init__(self, container: 'PowangArray', index: int):
        super().__init__(None)
        self.container = container
        self.index = index
        self.defined = True

    def get(self) -> 'PowangAny':
        return self.container.data[self.index]

    def set(self, value: 'PowangAny') -> None:
        self.container.data[self.index] = value

    def __repr__(self) -> str:
        return f"<reference: element {self.index}>"


class PowangPropertyReference(PowangTypeBase):
    """A reference to one public property of an object."""

    type: Literal['reference'] = 'reference'

    def __init__(self, container: 'PowangObjectType', name: str):
        super().__init__(None)
        self.container = container
        self.name = name
        self.defined = True

    def get(self) -> 'PowangAny':
        value = self.container.getProperty(self.name, False)
        if value is None:
            raise KeyError(self.name)
        return value

    def set(self, value: 'PowangAny') -> None:
        self.container.data[self.name] = value

    def __repr__(self) -> str:
        return f"<reference: property {self.name}>"

# ====== REFERENCE =========
class PowangReference(PowangTypeBase):
    type: Literal['reference'] = 'reference'

    def __init__(self, owner: dict[str, Any], name: str, target_type: str = 'any'):
        super().__init__(None)
        self.owner = owner
        self.name = name
        self.target_type = target_type
        self.defined = True

    def get(self) -> 'PowangAny':
        return self.owner[self.name]

    def set(self, value: 'PowangAny') -> None:
        self.owner[self.name] = value

    def __repr__(self) -> str:
        return f"<reference: {self.name}>"


# ====== MODULE =========
class PowangModule(PowangTypeBase):
    """An immutable namespace produced by loading a Powang module.

    ``data`` maps each exported name to its runtime value. Functions are kept
    as overload lists so calls resolve exactly like unqualified calls do.
    """

    data: dict[str, Any]
    type: Literal['module'] = 'module'

    def __init__(self, name: str = '', members: Optional[dict[str, Any]] = None):
        super().__init__(dict(members) if members is not None else {})
        self.name = name
        self.legacy = False

    def getMember(self, name: str):
        return self.data.get(name)

    def __repr__(self) -> str:
        return f'<module: {self.name}>'

# ====== TASK =========
class PowangTask(PowangTypeBase):
    """A handle to work running on the interpreter's task pool.

    The value itself is only a handle: the result, the error and the cancel
    flag are filled in by the worker thread. Every access to the mutable
    fields goes through ``lock`` so the parent thread can inspect a task while
    a worker is still writing it.

    Copy semantics are intentionally *reference* semantics: a task names one
    piece of running work, so copying the handle must not fork the work.
    """

    type: Literal['task'] = 'task'

    def __init__(self, task_id: int = 0):
        super().__init__(task_id)
        self.task_id: int = task_id
        self.status: str = 'pending'
        self.result: Optional['PowangAny'] = None
        self.error: Optional[BaseException] = None
        self.cancel_requested: bool = False
        self.future: Any = None
        self.handled: bool = False
        self.lock: Lock = Lock()

    def __repr__(self) -> str:
        with self.lock:
            return f'<task: {self.task_id} {self.status}>'

# ====== ANY =========
PowangAny = Union[
    PowangNova,        # None
    PowangAnyType,        # Any
    PowangBoolean,     # bool
    PowangInteger,     # int
    PowangNumber,      # float
    PowangString,      # str
    PowangArray,       # list
    PowangMap,         # dict
    PowangFunction,    # FunctionType
    PowangObjectType,  # object
    PowangFileStream,  # TextIO handle
    PowangErrorValue,  # catchable error value
    PowangModule,      # imported namespace
    PowangTask,        # running task handle
    PowangReference,   # temporary variable reference
    PowangTuple,       # fixed-size tuple
]

def PowangTypeMap(type: str) -> Callable[(...), PowangAny]:
    return {
        PowangNova.type       : PowangNova,
        PowangAnyType.type       : PowangAnyType,
        PowangInteger.type    : PowangInteger,
        PowangNumber.type     : PowangNumber,
        PowangBoolean.type    : PowangBoolean,
        PowangString.type     : PowangString,
        PowangArray.type      : PowangArray,
        PowangMap.type        : PowangMap,
        PowangFunction.type   : PowangFunction,
        PowangObjectType.type : PowangObjectType,
        PowangFileStream.type : PowangFileStream,
        PowangErrorValue.type : PowangErrorValue,
        PowangModule.type     : PowangModule,
        PowangTask.type       : PowangTask,
        PowangTuple.type      : PowangTuple,
    }[type]

def PowangCopyConstruct(any: PowangAny) -> PowangAny:
    if any.type == PowangObjectType.type:
        return PowangCopyConstructObjectType(any)
    if any.type == PowangFileStream.type:
        # File streams are external resources: a "copy" is the same stream
        # reference, never a new PowangFileStream (which would need mode/open).
        return any
    if any.type == PowangErrorValue.type:
        # Error values are immutable snapshots; sharing the reference is safe.
        return any
    if any.type == PowangModule.type:
        # Modules are immutable namespaces; copies stay the same reference.
        return any
    if any.type == PowangTask.type:
        # A task handle names one piece of running work. Copying it must not
        # duplicate or restart that work, so the reference is preserved.
        return any
    if any.type == PowangTuple.type:
        return PowangTuple(list(any.data))
    if any.type == PowangReference.type:
        # A reference is an alias, not a value. Copying it must keep pointing
        # at the same slot, so the reference itself is preserved.
        return any
    if any.type == PowangErrorValue.type:
        ## Preserve the structured payload (kind, message, details) across
        ## copies; only `data` holds the printable form.
        value = PowangErrorValue(any.data)
        value.error = any.error
    elif any.type == PowangFunction.type:
        value = PowangFunction(
            args     = list(any.args),
            data     = list(any.data),
            return_expr = any.return_expr,
        )
        value.min_argc = any.min_argc
        if hasattr(any, 'closure'):
            value.closure = any.closure
        if hasattr(any, 'external'):
            value.external = any.external
    else:
        value = PowangTypeMap(any.type)(any.data)
    value.weak = any.weak
    value.const = any.const
    return value

def PowangCopyConstructObjectType(anyType: PowangObjectType) -> PowangObjectType:
    # Props are copied by value, not by reference: instances must never share
    # mutable property state between each other nor with their base type.
    value = PowangObjectType(
        {key: PowangCopyConstruct(prop) for key, prop in anyType.data.items()},
        {key: PowangCopyConstruct(prop) for key, prop in anyType.private_props.items()},
        {key: list(methods) for key, methods in anyType.public_meths.items()},
        {key: list(methods) for key, methods in anyType.private_meths.items()},
    )
    value.type_name = anyType.type_name
    value.is_enum = getattr(anyType, 'is_enum', False)
    value.weak = anyType.weak
    value.const = anyType.const
    return value

def PowangTypeCast(type: str, any: PowangAny) -> PowangAny | None:
    return PowangTypeMap(type).cast(any) # type: ignore