from typing import Union, Literal, Any, Callable
from abc import abstractmethod

OperationFunc = Callable[['PowangAny'], 'PowangAny']
OperationName = Literal['addition'] | Literal['substraction'] | Literal['multiplication'] | Literal['division']

class PowangType_Base:
    type: Any = None

    def __init__(self, data, *, const: bool = False):
        self.data = data
        self.const = const

    def addition(self, right: 'PowangAny') -> 'PowangAny': # type: ignore
        pass
    
    def substraction(self, right: 'PowangAny') -> 'PowangAny': # type: ignore
        pass
    
    def multiplication(self, right: 'PowangAny') -> 'PowangAny': # type: ignore
        pass
    
    def division(self, right: 'PowangAny') -> 'PowangAny': # type: ignore
        pass

    def __eq__(self, value: object) -> bool:
        if isinstance(value, PowangType_Base):
            return self.data == value.data
        return False

    def __repr__(self):
        return f'PowangType({self.type} {'const' if self.const else 'mutable'}: {self.data})'
    
# ====== NOV =========
class PowangNov(PowangType_Base):
    data: None
    type: Literal['nov'] = 'nov'
    def __init__(self, data: None = None, *, const=False):
        super().__init__(None, const=const)

# ====== BOOL =========
class PowangBool(PowangType_Base):
    data: bool
    type: Literal['bool'] = 'bool'
    def __init__(self, data: bool, *,
        const: bool = False
    ):
        super().__init__(data, const=const)
        self.data = data

    @staticmethod
    def eval_expression(expression: 'PowangAny'):
        result = PowangBool(False)
        if expression.type == PowangBool.type:
            result.data = expression.data
        elif expression.type == PowangNumber.type:
            result.data = expression.data != 0.0
        elif expression.type == PowangString.type or expression.type == PowangList.type:
            result.data = len(expression.data) > 0
        # elif expression.type == PowangNov.type:
        #     return False
        return result

    def addition(self, right: 'PowangAny'):
        return PowangBool(self.data or PowangBool.eval_expression(right).data)

    def substraction(self, right: 'PowangAny'):
        return PowangBool(self.data or not PowangBool.eval_expression(right).data)

    def multiplication(self, right: 'PowangAny'):
        return PowangBool(self.data and PowangBool.eval_expression(right).data)

    def division(self, right: 'PowangAny'):
        return PowangBool(self.data and not PowangBool.eval_expression(right).data)

# ====== NUMBER =========
class PowangNumber(PowangType_Base):
    data: float
    type: Literal['number'] = 'number'
    def __init__(self, data: float, *,
        const: bool = False
    ):
        super().__init__(data, const=const)

    def get_number(self):
        """returns an integer if its possible, else returns a float"""
        return int(self.data) if self.data.is_integer() else self.data

    def addition(self, right: 'PowangAny'):
        if right.type == PowangBool.type:
            return PowangNumber(self.data + [0.0, 1.0][right.data])
        if right.type == PowangNumber.type:
            return PowangNumber(self.data + right.data)
        if right.type == PowangString.type:
            return PowangString(str(self.get_number()) + right.data)
        if right.type == PowangList.type:
            return PowangNumber(self.data + len(right.data))
        return PowangNov()

    def substraction(self, right: 'PowangAny'):
        if right.type == PowangBool.type:
            return PowangBool.eval_expression(self).substraction(right)
        if right.type == PowangNumber.type:
            return PowangNumber(self.data - right.data)
        if right.type == PowangString.type:
            return PowangString(right.data + str(self.get_number()))
        if right.type == PowangList.type:
            return PowangList(right.data[int(self.data):])
        return PowangNov()

    def multiplication(self, right: 'PowangAny'):
        if right.type == PowangBool.type:
            return PowangBool.eval_expression(self).multiplication(right)
        if right.type == PowangNumber.type:
            return PowangNumber(self.data * right.data)
        if right.type == PowangString.type:
            return PowangString(right.data * int(self.data))
        if right.type == PowangList.type:
            return PowangList(right.data * int(self.data))
        return PowangNov()

    def division(self, right: 'PowangAny'):
        if right.type == PowangBool.type:
            return PowangBool.eval_expression(self).division(right)
        if right.type == PowangNumber.type:
            return PowangNumber(self.data / right.data)
        if right.type == PowangString.type:
            return PowangList([PowangString(right.data[i:i + int(self.data)]) for i in range(0, len(right.data), int(self.data))])
        if right.type == PowangList.type:
            return PowangList([PowangList([PowangCopyConstruct(element) for element in right.data[i:i + int(self.data)]]) for i in range(0, len(right.data), int(self.data))])
        return PowangNov()

# ====== STRING =========
class PowangString(PowangType_Base):
    data: str
    type: Literal['string'] = 'string'
    def __init__(self, data: str, *,
        const: bool = False
    ):
        super().__init__(data, const=const)

    def addition(self, right: 'PowangAny'):
        if right.type == PowangBool.type:
            return PowangBool.eval_expression(self).addition(right)
        if right.type == PowangNumber.type:
            return PowangString(self.data + chr(int(right.data)))
        if right.type == PowangString.type:
            return PowangString(self.data + right.data)
        if right.type == PowangList.type:
            result = PowangString(self.data)
            for element in right.data:
                result = result.addition(element)
            return result
        return PowangNov()

    def substraction(self, right: 'PowangAny'):
        if right.type == PowangBool.type:
            return PowangBool.eval_expression(self).substraction(right)
        if right.type == PowangNumber.type:
            return PowangString(chr(int(right.data)) + self.data)
        if right.type == PowangString.type:
            return PowangString(self.data.replace(right.data, '', 1))
        if right.type == PowangList.type:
            result = PowangString(self.data)
            for element in right.data:
                result = result.addition(element)
            return result
        return PowangNov()

    def multiplication(self, right: 'PowangAny'):
        if right.type == PowangBool.type:
            return PowangBool.eval_expression(self).multiplication(right)
        if right.type == PowangNumber.type:
            return right.multiplication(self)
        if right.type == PowangString.type:
            return PowangNumber(self.data.count(right.data))
        if right.type == PowangList.type:
            result = PowangString(self.data)
            for element in right.data:
                result = result.addition(element)
            return result
        return PowangNov()

    def division(self, right: 'PowangAny'):
        if right.type == PowangBool.type:
            return PowangBool.eval_expression(self).division(right)
        if right.type == PowangNumber.type:
            return PowangList([PowangString(self.data[i - int(right.data):i]) for i in range(len(self.data), 0, -int(right.data))])
        if right.type == PowangString.type:
            return PowangList([PowangString(part) for part in self.data.split(right.data)])
        if right.type == PowangList.type:
            result = PowangString(self.data)
            for element in right.data:
                result = result.division(element)
            return result
        return PowangNov()
    
# ====== LIST =========
class PowangList(PowangType_Base):
    data: list['PowangAny']
    type: Literal['list'] = 'list'
    def __init__(self, data: list['PowangAny'], *,
        const: bool = False
    ):
        super().__init__(data, const=const)

    def addition(self, right: 'PowangAny'):
        if right.type == PowangBool.type:
            return PowangBool.eval_expression(self).addition(right)
        if right.type == PowangNumber.type:
            return PowangList(self.data + [right])
        if right.type == PowangString.type:
            return PowangList(self.data + [right])
        if right.type == PowangList.type:
            return PowangList(self.data + right.data)
        return PowangNov()

    def substraction(self, right: 'PowangAny'):
        if right.type == PowangBool.type:
            return PowangBool.eval_expression(self).substraction(right)
        if right.type == PowangNumber.type:
            return PowangList(self.data[:-int(right.data)])
        if right.type == PowangString.type:
            return self.substraction(PowangList([PowangNumber(ord(ch)) for ch in right.data]))
        if right.type == PowangList.type:
            result = PowangList(self.data)
            for element in right.data:
                while element in result.data:
                    result.data.remove(element)
            return result
        return PowangNov()

    def multiplication(self, right: 'PowangAny'):
        if right.type == PowangBool.type:
            return PowangBool.eval_expression(self).multiplication(right)
        if right.type == PowangNumber.type:
            return PowangNumber(float(self.data.count(right)))
        if right.type == PowangString.type:
            return PowangNumber(float(self.data.count(right)))
        if right.type == PowangList.type:
            result = PowangList(self.data)
            for element in right.data:
                result = result.multiplication(element)
            return result
        return PowangNov()

    def division(self, right: 'PowangAny'):
        if right.type == PowangBool.type:
            return PowangBool.eval_expression(self).division(right)
        if right.type == PowangNumber.type:
            return PowangList(self.data[::int(right.data)])
        if right.type == PowangString.type:
            self.division(PowangList([PowangNumber(ord(ch)) for ch in right.data]))
        if right.type == PowangList.type:
            result = PowangList(self.data)
            for element in right.data:
                result = result.division(element)
            return result
        return PowangNov()

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
class PowangStruct(PowangType_Base):       # user defined types
    data: dict[str, 'PowangAny']           # properties
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

# ====== ANY =========
PowangAny = Union[
    PowangNov,    # None
    PowangBool,   # bool
    PowangNumber, # float
    PowangString, # str
    PowangList,   # list
    PowangStruct, # object
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