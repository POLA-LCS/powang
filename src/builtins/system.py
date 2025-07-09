from ..powang_types import *
from subprocess import run

def builtin_system(prompt: PowangAny):
    assert prompt.type == PowangString.type, powang_error_type_match("builtin: system", PowangString.type, prompt.type)
    return PowangInteger(run(prompt.data, shell=True).returncode)