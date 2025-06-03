from typing import Union, Literal, Any

class PolangTypeBase:
    type: Any = None
    def __init__(self, data, *, const: bool = False):
        self.data = data
        self.const = const
        
    def __repr__(self):
        return f'PolangTypeBase({self.type} {'const' if self.const else 'mutable'}: {self.data})'

# ====== NUMBER =========
class PolangNumber(PolangTypeBase):
    data: float
    type: Literal['number'] = 'number'
    def __init__(self, data: float, *,
        const: bool = False
    ):
        super().__init__(data, const=const)
        
    def __add__(self, right: 'PolangNumber'):
        return PolangNumber(self.data + right.data)
    
    def __sub__(self, right: 'PolangNumber'):
        return PolangNumber(self.data - right.data)
    

# ====== STRING =========
class PolangString(PolangTypeBase):
    data: str
    type: Literal['string'] = 'string'
    def __init__(self, data: str, *,
        const: bool = False
    ):
        super().__init__(data, const=const)

# ====== LIST =========
class PolangList(PolangTypeBase):
    data: list['PolangAny']
    type: Literal['list'] = 'list'
    def __init__(self, data: list['PolangAny'], *,
        const: bool = False
    ):
        super().__init__(data, const=const)
        
# ====== STRUCT ========= TODO
class PolangStruct(PolangTypeBase):
    data: dict[str, 'PolangAny']
    type: Literal['struct'] = 'struct'
    def __init__(self, data: dict[str, 'PolangAny'], *,
        const: bool = False
    ):
        super().__init__(data, const=const)

# ====== NOV =========
class PolangNov(PolangTypeBase):
    data: None
    type: Literal['nov'] = 'nov'
    def __init__(self):
        super().__init__(None)

# ====== ANY =========
PolangAny = Union[
    PolangNov,
    PolangNumber,
    PolangString,
    PolangList,
    PolangStruct,
]

# ====== ERROR =========
class PolangError(PolangTypeBase):
    data: str
    type: Literal['error'] = 'error'
    def __init__(self, data: str):
        super().__init__(data, const=True)
