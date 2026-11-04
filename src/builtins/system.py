from ..powang_types import *
from ..state import get_state
from subprocess import run

def builtin_system(prompt: PowangAny):
    assert prompt.type == PowangString.type, powang_error_type_match("builtin: system", PowangString.type, prompt.type)
    state = get_state()
    ## `system` runs through the shell, so it is a command-injection surface.
    ## While a server is running, refuse by default: a handler that forwards
    ## untrusted input to the shell must be an explicit decision.
    if state.http_servers and not getattr(state, 'allow_system', False):
        raise powang_throw(powang_error_format(
            'SECURITY',
            'builtin: system',
            'system() is disabled while an HTTP server is running',
            [
                'pass --allow-system or set POWANG_ALLOW_SYSTEM=1 to override',
                'never pass untrusted input to system()',
            ],
        ))
    return PowangInteger(run(prompt.data, shell=True).returncode)
