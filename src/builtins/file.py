from ..powang_types import *
from ..error import require
from ..state import get_state
from .cast import *

from typing import IO


def _file_streams() -> dict[str, IO]:
    ## The table is owned by the active InterpreterState. Two states may open
    ## the same filename without sharing or closing each other's handle.
    return get_state().file_streams


MODE_MAP: dict[str, str] = {
    "read": "r",
    "write": "w",
    "append": "a",
    "write+": "w+",
    "append+": "a+"
}

MAP_MODE: dict[str, str] = {value: key for key, value in MODE_MAP.items()}

def builtin_open(file_name: PowangAny, file_mode: PowangAny = PowangString("read")) -> PowangBoolean:
    require(file_name.type == PowangString.type, lambda: powang_error_type_match('builtin: open, name', PowangString.type, file_name.type))
    require(file_mode.type == PowangString.type, lambda: powang_error_type_match('builtin: open, name', PowangString.type, file_mode.type))    
    require(file_mode.data in MODE_MAP, lambda: powang_error_format('VALUE', 'builtin: open, mode', f"Invalid mode: {file_mode.data}", [
        f"valid modes are: {', '.join(MODE_MAP)}"
    ]))
    try:
        textio: IO = open(file_name.data, MODE_MAP[file_mode.data])
        _file_streams()[file_name.data] = textio
        return PowangBoolean(True)
    except OSError:
        return PowangBoolean(False)

def builtin_write(file_name: PowangAny, lines: PowangAny) -> PowangBoolean:
    require(file_name.type == PowangString.type, lambda: powang_error_type_match('builtin: write, name', PowangString.type, file_name.type))
    if lines.type != PowangArray.type:
        lines = PowangArray([lines])
    file_streams = _file_streams()
    require(file_name.data in file_streams, lambda: powang_error_format('VALUE', 'builtin: write', f"File is not opened: {file_name.data}"))
    lines_to_write: list[str] = []
    for line in lines.data:
        casted_line = explicitCastString(line)
        if casted_line is None:
            raise powang_throw(powang_error_invalid_cast(
                'builtin: write', PowangString.type, line.type, True
            ))
        lines_to_write.append(casted_line.data)
    file_streams[file_name.data].writelines(lines_to_write)
    return PowangBoolean(True)

def builtin_read(file_name: PowangAny) -> PowangString:
    require(file_name.type == PowangString.type, lambda: powang_error_type_match('builtin: read, name', PowangString.type, file_name.type))
    file_streams = _file_streams()
    require(file_name.data in file_streams, lambda: powang_error_format('VALUE', 'builtin: read', f"File is not opened: {file_name.data}"))
    file_stream = file_streams[file_name.data]
    require(file_stream.mode in {
        MODE_MAP["read"],
        MODE_MAP["write+"],
        MODE_MAP["append+"],
    }, lambda: powang_error_format('LOGIC', 'builtin: read', "File must be in a readable mode to read", [
        f"file is in the {MAP_MODE[file_stream.mode]}"
    ]))
    return PowangString(file_streams[file_name.data].read())

def builtin_close(file_name: PowangAny) -> PowangBoolean:
    require(file_name.type == PowangString.type, lambda: powang_error_type_match('builtin: close, name', PowangString.type, file_name.type))
    file_streams = _file_streams()
    require(file_name.data in file_streams, lambda: powang_error_format('VALUE', 'builtin: close', f"File is not opened: {file_name.data}"))
    file_stream = file_streams.pop(file_name.data)
    file_stream.close()
    return PowangBoolean(True)