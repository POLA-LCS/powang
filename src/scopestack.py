"""Lexical scope facade.

The real scope stacks live on ``src.state.InterpreterState`` so each execution
context owns its own state. ``ScopeStack`` is a class-level proxy: every
attribute and method delegates to the scope of the state currently selected by
``src.state.CURRENT_STATE``.

Keeping the proxy means the runtime's many ``ScopeStack.push()`` /
``ScopeStack.return_value`` call sites did not have to change when the stacks
moved off the class object.
"""

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


_get_state = None


def _scope():
    ## Imported lazily: ``src.state`` imports ``ScopeType`` from this module,
    ## so a module-level import here would be circular. The function reference
    ## is cached after the first call to keep the proxy cheap.
    global _get_state
    if _get_state is None:
        from .state import get_state
        _get_state = get_state
    return _get_state().scope


class _ScopeStackMeta(type):
    """Delegate class attribute access to the active state's scope."""

    @property
    def return_value(cls):
        return _scope().return_value

    @return_value.setter
    def return_value(cls, value):
        _scope().return_value = value

    @property
    def important(cls):
        return _scope().important

    @important.setter
    def important(cls, value):
        _scope().important = value

    @property
    def method_call_stack(cls):
        return _scope().method_call_stack

    @method_call_stack.setter
    def method_call_stack(cls, value):
        _scope().method_call_stack = value

    @property
    def variables(cls):
        return _scope().variables

    @variables.setter
    def variables(cls, value):
        _scope().variables = value

    @property
    def functions(cls):
        return _scope().functions

    @functions.setter
    def functions(cls, value):
        _scope().functions = value

    @property
    def ObjectTypes(cls):
        return _scope().ObjectTypes

    @ObjectTypes.setter
    def ObjectTypes(cls, value):
        _scope().ObjectTypes = value

    @property
    def wildcard_sources(cls):
        return _scope().wildcard_sources

    @wildcard_sources.setter
    def wildcard_sources(cls, value):
        _scope().wildcard_sources = value

    def get_variable(cls, name: str) -> Optional[PowangAny]:
        return _scope().get_variable(name)

    def find_variable_slot(cls, name: str):
        return _scope().find_variable_slot(name)

    def get_functions(cls, name: str) -> list[PowangFunction] | None:
        return _scope().get_functions(name)

    def get_ObjectType(cls, name: str) -> PowangObjectType | None:
        return _scope().get_ObjectType(name)

    def get_wildcard_source(cls, name: str) -> str | None:
        return _scope().get_wildcard_source(name)

    def new_wildcard_source(cls, name: str, source: str):
        return _scope().new_wildcard_source(name, source)

    def get_existingObjectType(cls, name: str) -> PowangObjectType:
        return _scope().get_existingObjectType(name)

    def new_variable(cls, name: str, value: PowangAny):
        return _scope().new_variable(name, value)

    def new_function(cls, name: str, value: PowangFunction):
        return _scope().new_function(name, value)

    def new_ObjectType(cls, name: str, value: PowangObjectType):
        return _scope().new_ObjectType(name, value)

    def current_scope_type(cls) -> ScopeType:
        return _scope().current_scope_type()

    def pop(cls):
        return _scope().pop()

    def push(cls, scope_type: ScopeType | None = None):
        return _scope().push(scope_type)

    def push_captured(cls, variables: dict[str, PowangAny],
                      functions: dict[str, list[PowangFunction]],
                      object_types: dict[str, PowangObjectType]):
        return _scope().push_captured(variables, functions, object_types)

    def save_scopes(cls):
        return _scope().save_scopes()

    def reset_scopes(cls):
        return _scope().reset_scopes()

    def restore_scopes(cls, state):
        return _scope().restore_scopes(state)


class ScopeStack(metaclass=_ScopeStackMeta):
    """Compatibility facade over the active per-execution ``ScopeState``."""

    pass
