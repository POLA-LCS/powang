from src import *
from sys import argv

def print_usage():
    print('Powang X usage:')
    print('    powang                  Runs the REPL.')
    print('    powang (--help | -h)    Display this message.')
    print('    powang input.po         Interprets an input.')
    print('FLAGS:')
    print('    --ast output.json       Dumps the ast tree into a json.')
    return 1

def inicialize_repl():
    print('repl not implemented yet')

import pathlib
PATHS['ABSOLUTE'] = pathlib.Path(__file__).resolve()

def arguments_handler(args: list[str]):
    input_file: str | None = None
    ast_output: str | None = None
    
    if len(args) == 0:
        return 0
    
    for arg in args:
        if ast_output is not None and ast_output == '':
            ast_output = arg
        elif arg.startswith('--'):
            arg = arg[2:]
            if arg in {'help', 'h'}:
                return 1
            elif arg == 'ast':
                ast_output = ''
            else:
                raise powang_throw(powang_error_format('USAGE', None, 'Invalid flag for powang file', [
                    f"invalid flag: {arg}"
                ]))
        elif input_file is not None:
            raise powang_throw(powang_error_format('USAGE', None, 'Input already provided', [input_file]))
        else:
            input_file = arg
    
            
    if ast_output is not None:
        assert ast_output, powang_error_format('USAGE', None, 'dump output was nos provided')
    return input_file, ast_output

def main(args: list[str]):
    result = arguments_handler(args)
    if isinstance(result, int):
        if result == 0:
            return inicialize_repl()
        elif result == 1:
            return print_usage()
    
    input_file, ast_output = result

    if input_file:
        PATHS['RELATIVE'] = Path(input_file).resolve()
        content = get_file_content(input_file)
        interpretation_result = interpret_program(content, ast_output)
        if isinstance(interpretation_result, (int, float)):
            return int(interpretation_result)
        return -1
            
if __name__ == "__main__":
    exit_code: int = 0
    try:
        result = main(argv[1:])
        if result is not None:
            exit_code = result
    except AssertionError as ass:
        print(ass)
    except KeyboardInterrupt as kinter:
        print()
        print(powang_error_format("KEYBOARD", "User input", "Keyboard interrupt"))
    except FileNotFoundError as ferror:
        print(powang_error_format("INPUT", "File read", f"File not founded: {ferror.filename}"))
    while (keys := list(FILE_STREAMS.keys())):
        FILE_STREAMS.pop(keys[-1])
    exit(exit_code)