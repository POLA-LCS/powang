from .powang_types import *
from enum import Enum, auto

class ScopeType(Enum):
    GLOBAL   = auto()
    FUNCTION = auto()
    TYPE     = auto()

    @staticmethod
    def toStr(token_type: 'ScopeType'):
        if token_type.value not in token_type._value2member_map_:
            raise ValueError(f"Unknown scope type: {token_type}")
        return ' '.join(word.lower() for word in token_type.name.split('_'))

class ScopeStack:
    return_value: PowangAny | None = None
    important: list[ScopeType] = [ScopeType.GLOBAL]
    method_call_stack: list[PowangUserType] = []

    variables: list[dict[str, PowangAny          ]]  = [{}]
    functions: list[dict[str, list[PowangFunction]]] = [{}]
    userTypes: list[dict[str, PowangUserType     ]]  = [{}]

    @staticmethod
    def get_variable(name: str) -> Optional[PowangAny]:
        for scope in ScopeStack.variables[::-1]:
            if (value := scope.get(name)) is not None:
                return value
        return None

    @staticmethod
    def get_functions(name: str) -> list[PowangFunction] | None:
        for scope in ScopeStack.functions[::-1]:
            if (func := scope.get(name)) is not None:
                return func
        return None

    @staticmethod
    def get_userType(name: str) -> PowangUserType | None:
        for scope in ScopeStack.userTypes[::-1]:
            if (type := scope.get(name)) is not None:
                return type
        return None
    
    @staticmethod
    def get_existingUserType(name: str) -> PowangUserType:
        assert (value := ScopeStack.get_userType(name)) is not None, powang_error_identifier_not_found("user type get", name, [
            "user type doesn't exists"
        ])
        return value

    @staticmethod
    def new_variable(name: str, value: PowangAny):
        ScopeStack.variables[-1][name] = value
        return value

    @staticmethod
    def new_function(name: str, value: PowangFunction):
        ScopeStack.functions[-1].setdefault(name, []).append(value)
        return value

    @staticmethod
    def new_userType(name: str, value: PowangUserType):
        ScopeStack.userTypes[-1][name] = value
        return value
        
    @staticmethod
    def pop():
        if len(ScopeStack.variables) == len(ScopeStack.important):
            ScopeStack.important.pop()
        ScopeStack.variables.pop()
        ScopeStack.functions.pop()
        ScopeStack.userTypes.pop()
        return True

    @staticmethod
    def push(scope_type: ScopeType | None = None):
        if scope_type is not None:
            ScopeStack.important.append(scope_type)
        ScopeStack.variables.append({})
        ScopeStack.functions.append({})
        ScopeStack.userTypes.append({})
        return True