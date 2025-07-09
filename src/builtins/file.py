from ..powang_types import *

from typing import IO

FILE_STREAMS: dict[str, IO] = {}

MODE_MAP: dict[str, str] = {
    "read": "r",
    "write": "w",
    "append": "a",
    "write+": "w+",
    "append+": "a+"
}

def builtin_open(file_name: PowangAny, file_mode: PowangAny = PowangString("read")) -> PowangBoolean:
    assert file_name.type == PowangString.type, powang_error_type_match('builtin: open, name', PowangString.type, file_name.type)
    assert file_mode.type == PowangString.type, powang_error_type_match('builtin: open, name', PowangString.type, file_mode.type)    
    
    assert file_mode.data in MODE_MAP, powang_error_format('VALUE', 'builtin: open, mode', f"Invalid mode: {file_mode.data}", [
        f"valid modes are: {', '.join(MODE_MAP)}"
    ])
    
    try:
        textio: IO = open(file_name.data, MODE_MAP[file_mode.data])
        FILE_STREAMS[file_name.data] = textio
        return PowangBoolean(True)
    except FileNotFoundError:
        return PowangBoolean(False)

def builtin_write(file_name: PowangAny, lines: PowangAny) -> PowangBoolean:
    assert file_name.type == PowangString.type, powang_error_type_match('builtin: write, name', PowangString.type, file_name.type)
    assert lines.type == PowangArray.type, powang_error_type_match('builtin: write', PowangArray.type, lines.type)
    assert file_name.data in FILE_STREAMS, powang_error_format('VALUE', 'builtin: write', f"File is not opened: {file_name.data}")
    FILE_STREAMS[file_name.data].writelines([str(line.data) for line in lines.data])
    return PowangBoolean(True)

def builtin_close(file_name: PowangAny) -> PowangBoolean:
    assert file_name.type == PowangString.type, powang_error_type_match('builtin: close, name', PowangString.type, file_name.type)
    assert file_name.data in FILE_STREAMS, powang_error_format('VALUE', 'builtin: close', f"File is not opened: {file_name.data}")
    FILE_STREAMS.pop(file_name.data)
    return PowangBoolean(True)