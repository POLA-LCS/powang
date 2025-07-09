from src import *
import json

def get_file_content(path: str) -> str:
    with open(path, 'r', encoding='utf-8') as file:
        content = file.read()
        if not content.endswith('\n'):
            content = content + '\n'
        return content

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
        content = get_file_content(input_file)

        program_parser = Parser(content)
        try:
            program_raw_ast = program_parser.parse()
            interpretation_result = interpret_program(program_raw_ast)

            if ast_output:
                def make_json_serializable(raw_ast):
                    if isinstance(raw_ast, dict):
                        return {
                            key: make_json_serializable(value)
                            for key, value in raw_ast.items()
                        }
                    elif isinstance(raw_ast, (LexerTokenType, ParserTokenType)):
                        return TokenToString(raw_ast).upper()
                    elif isinstance(raw_ast, (list, tuple)):
                        return [make_json_serializable(item) for item in raw_ast]
                    else:
                        return raw_ast
                    
                ast_dict = make_json_serializable(program_raw_ast)

                with open(ast_output, 'w', encoding='utf-8') as json_ast:
                    json_ast.write(json.dumps(ast_dict, indent=4, ensure_ascii=False))
                    
            if isinstance(interpretation_result, (int, float)):
                return int(interpretation_result)
            return -1
        except AssertionError as ass:
            powang_throw(f"ln: {program_parser.tokenizer.row + 1} | " + ass.args[0])
            
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