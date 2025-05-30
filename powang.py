from sys import exit
from scripts import *

FLAG_WARNING : bool = False
FLAG_FLEX    : bool = False
FLAG_DISCREET: bool = False

ERRORS_LIST: list[str] = []

EXIT_CODE  : int       = 0
RUNNING    : bool      = True

def interpret_line(ln: int, sentence: list[Token], expression: bool) -> Value:
    """### RECURSIVE"""

    inst, rest = sentence[0], sentence[1:]

    if inst.type == TokenType.EXPRESSION:
        return force_value(interpret_line(ln, inst.value, True)) # type: ignore

    assert inst.type == TokenType.KEYWORD, INLINE_ERROR(ln,
        error_format_syntax('expecting valid instruction', f"inst? -> {inst}"))

    argc, is_flex, func = INSTRUCTIONS[inst.value] # type: ignore

    assert len(rest) == 1, INLINE_ERROR(ln,
        error_format_syntax("multiple arguments must be listed", ' '.join([str(tk) for  tk in rest]))
    )

    if rest[0].type != TokenType.EXPRESSION:
        rest = [Token(TokenType.EXPRESSION, rest)]

    assert (arg_count := len(rest[0].value)) <= argc or argc == -1, INLINE_ERROR(ln,
        error_format_ARGC(STACK[-1], f'not enough arguments for inst "{inst.value}"', argc, arg_count))

    try:
        return Value(func(*rest[0].value), True)
    except AssertionError as ass:
        error = INLINE_ERROR(ln, ass.args[0])
        assert FLAG_FLEX and is_flex, error # NORMAL ASSERT
        if FLAG_DISCREET:
            ERRORS_LIST.append(error)
        else:
            print(error)
        return Value(None, True)

def interpret_program(token_program: list[list[Token]]):
    global EXIT_CODE
    for ln, sentence in enumerate(token_program):
        if len(sentence) == 0: # IGNORE EMPTY LINES
            continue

        exit_code_value = interpret_line(ln, sentence, False)
        if exit_code_value.type == NUMBER:
            EXIT_CODE = int(exit_code_value.value) # type: ignore

def main(argc: int, argv: list[str]):
    if argc == 1:
        display_help()
        exit(0)

    global FLAG_WARNING
    global FLAG_FLEX
    global FLAG_DISCREET
    global EXIT_CODE

    input_file = None

    # Flag and files loop
    for arg in argv[1:]:
        if arg.startswith('--'):
            flag = arg[2:]
            option = None

            # FLAG TRIGGERS
            
            if ':' in flag:
                flag, option = flag.split(':')

            assert flag in ['warn', 'error', 'flex'], error_format('USAGE', None, f'Invalid flag', f'flag -> {flag}')
            if flag == 'warn':
                FLAG_WARNING = True
            elif flag == 'flex':
                FLAG_FLEX = True
                assert option is None or option == 'discreet', error_format('USAGE', None, "Invalid flag option", f'option -> {flag}\n    Expected: discreet')
                FLAG_DISCREET = True
        else:
            assert input_file is None, error_format('USAGE', None, "input already provided", f"input -> {input_file}")
            input_file = arg

    # File doesn't exist ERROR
    if input_file is None:
        print(error_format('USAGE', None, 'input was not provided'))
        display_help()
        EXIT_CODE = 1
        return

    file_content = get_file_content(input_file)

    token_program: list[list[Token]] = []

    for ln, line in enumerate(file_content):
        line_words = line.split(' ')
        token_program.append(tokenize_line(ln, line_words))

    interpret_program(token_program)

from sys import argv

if __name__ == '__main__':
    try:
        main(len(argv), argv)
    except AssertionError as ass:
        print('\r', ass)
    exit(EXIT_CODE) # END
    
# TODO: Change the "scope" thing...