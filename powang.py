from sys import exit
from scripts import *

def interpret_line(ln: int, sentence: list[Token], expression: bool) -> Value:
    """### RECURSIVE"""
    
    inst, rest = sentence[0], sentence[1:]
    
    if inst.type == TokenType.EXPRESSION:
        return force_value(interpret_line(ln, inst.value, True)) # type: ignore
    
    assert inst.type == TokenType.KEYWORD, INLINE(ln,
        ERROR_FORMAT_SYNTAX('expecting valid instruction', f"inst? -> {inst}"))
    
    argc, func = INSTRUCTIONS[inst.value] # type: ignore
    
    assert len(rest) >= argc or argc == -1, INLINE(ln,
        ERROR_FORMAT_INVALID_ARGUMENTS(STACK[-1], f'not enough arguments for inst "{inst.value}"', argc, len(rest)))

    if argc != -1 and len(rest[argc:]) > 0:
        return interpret_line(ln, rest[argc:], False)

    return Value(func(*rest), True)

def interpret_program(token_program: list[list[Token]], expression: bool = False):
    global EXIT_CODE
    for ln, sentence in enumerate(token_program):
        if len(sentence) == 0: # IGNORE EMPTY LINES
            continue
        
        exit_code_value = interpret_line(ln, sentence, False)
        if exit_code_value.type == Types.Number:
            EXIT_CODE = int(exit_code_value.value) # type: ignore

def main(argc: int, argv: list[str]):
    if argc == 1:
        display_usage()
        exit(0)

    global WARNING_ENABLE
    global STRICT_ASSERTS
    global ERRORS_AT_EXIT

    input_file = None

    # Flag and files loop
    for arg in argv[1:]:
        if arg.startswith('--'):
            flag = arg[2:]

            # FLAG TRIGGERS

            assert flag in ['warn', 'error', 'strict'], RAISE(ERROR_FORMAT('USAGE', 'input', f'Invalid flag', f'flag -> {flag}'))
            if flag == 'warn':
                WARNING_ENABLE = True
            elif flag == 'error':
                ERRORS_AT_EXIT = True
            elif flag == 'strict':
                STRICT_ASSERTS = True
        else:
            assert input_file is None, ERROR_FORMAT('USAGE', 'input', "input already provided", f"input -> {input_file}")
            input_file = arg

    # File doesn't exist ERROR
    assert input_file is not None, ERROR_FORMAT('USAGE', 'input', 'input was not provided')

    file_content = get_file_content(input_file)

    token_program: list[list[Token]] = []

    for ln, line in enumerate(file_content):
        line_words = line.split(' ')
        token_program.append(tokenize_line(ln, line_words))
    
    interpret_program(token_program, False)
    
from sys import argv

if __name__ == '__main__':
    try:
        main(len(argv), argv)
    except AssertionError as ass:
        print(ass)
    exit(EXIT_CODE) # END