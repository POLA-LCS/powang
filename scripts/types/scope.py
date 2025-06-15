from .native import PowangAny, PowangError
from typing import Callable

InstructionFormat = tuple[int, int, bool, Callable[(...), PowangAny | PowangError]]
MemoryType = dict[str, PowangAny]

class ScopeType:
    """### SINGLETON"""
    def __init__(self, data: dict[str, PowangAny]):
        self.name_stack: list[tuple[str, bool]] = [('global', False)]
        self.memory_stack: list[MemoryType] = [data]
        self.depth = 0

    def peek_name(self):
        return self.name_stack[-1]

    def peek_memory(self):
        return self.memory_stack[-1]

    def push(self, name: str, indent: bool):
        self.name_stack.append((name, indent))
        self.memory_stack.append({})
        self.depth += 1 if indent else 0
        return self

    def pop(self, times=1):
        for i in range(times):
            _, indent = self.name_stack.pop()
            if indent:
                self.depth -= 1
            self.memory_stack.pop()
        return self

    def set_memory(self, var_name: str, var_value: PowangAny, where: str):
        for i, scope in enumerate(reversed(self.name_stack)):
            scope_name, _ = scope
            if scope_name == where:
                self.memory_stack[-i - 1].setdefault(var_name, var_value).data = var_value.data # type: ignore
        return self

    def get_memory(self, name: str):
        for scope, memory in zip(self.name_stack[::-1], self.memory_stack[::-1]):
            if (value := memory.get(name)) is not None:
                return (scope, value)
        return None