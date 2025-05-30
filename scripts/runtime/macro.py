class Macro:
    def __init__(self, name: str, argc: int, code: list[str] = []):
        self.name = name
        self.argc = argc
        self.code = code

    def __repr__(self) -> str:
        return f'{self.name}({self.argc})[{len(self.code)}]'