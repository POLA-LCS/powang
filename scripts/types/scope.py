from .native import PowangAny, PowangError
from typing import Callable

InstructionFormat = tuple[int, int, bool, Callable[(...), PowangAny | PowangError]]
MemoryType = dict[str, PowangAny]

class MemoryScopeHandler:
    class Scope:
        def __init__(self, name: str, indents: bool):
            self.name: str = name
            self.indents: bool = indents
            
    """### SINGLETON"""
    def __init__(self, data: dict[str, PowangAny]):
        self.scope_stack: list[MemoryScopeHandler.Scope] = [MemoryScopeHandler.Scope('global', False)]
        self.memory_stack: list[MemoryType] = [data]
        self.indent_depth: int = 0

    def peek_scope(self):
        return self.scope_stack[-1]

    def peek_memory(self):
        return self.memory_stack[-1]

    def push(self, name: str, indent: bool):
        self.scope_stack.append(MemoryScopeHandler.Scope(name, indent))
        self.memory_stack.append({})
        self.indent_depth += 1 if indent else 0
        return self

    def pop(self, times=1):
        for i in range(times):
            scope = self.scope_stack.pop()
            if scope.indents:
                self.indent_depth -= 1
            self.memory_stack.pop()
        return self

    def set_memory(self, var_name: str, var_value: PowangAny, where: str):
        for i, scope in enumerate(reversed(self.scope_stack)):
            if scope.name == where:
                self.memory_stack[-i - 1][var_name] = var_value
        return self

    def get_memory(self, name: str):
        for scope, memory in zip(self.scope_stack[::-1], self.memory_stack[::-1]):
            if (value := memory.get(name)) is not None:
                return (scope, value)
        return None