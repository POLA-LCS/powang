from ..powang_types import *
from .cast import *

from typing import IO

FILE_STREAMS: dict[str, IO] = {}

MODE_MAP: dict[str, str] = {
    "read": "r",
    "write": "w",
    "append": "a",
    "write+": "w+",
    "append+": "a+"
}

MAP_MODE: dict[str, str] = {value: key for key, value in MODE_MAP.items()}

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
    if lines.type != PowangArray.type:
        lines = PowangArray([lines])
    assert file_name.data in FILE_STREAMS, powang_error_format('VALUE', 'builtin: write', f"File is not opened: {file_name.data}")
    FILE_STREAMS[file_name.data].writelines([explicitCastString(line) for line in lines.data])
    return PowangBoolean(True)

def builtin_read(file_name: PowangAny) -> PowangString:
    assert file_name.type == PowangString.type, powang_error_type_match('builtin: read, name', PowangString.type, file_name.type)
    assert file_name.data in FILE_STREAMS, powang_error_format('VALUE', 'builtin: read', f"File is not opened: {file_name.data}")
    file_stream = FILE_STREAMS[file_name.data]
    assert file_stream.mode in {
        MODE_MAP["read"],
        MODE_MAP["write+"],
        MODE_MAP["append+"],
    }, powang_error_format('LOGIC', 'builtin: read', "File must be in a readable mode to read", [
        f"file is in the {MAP_MODE[file_stream.mode]}"
    ])
    return PowangString(FILE_STREAMS[file_name.data].read())

def builtin_close(file_name: PowangAny) -> PowangBoolean:
    assert file_name.type == PowangString.type, powang_error_type_match('builtin: close, name', PowangString.type, file_name.type)
    assert file_name.data in FILE_STREAMS, powang_error_format('VALUE', 'builtin: close', f"File is not opened: {file_name.data}")
    FILE_STREAMS.pop(file_name.data)
    return PowangBoolean(True)