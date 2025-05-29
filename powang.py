from sys import exit
from scripts import *
from icecream import ic

def main(argc: int, argv: list[str]):
    if argc == 1:
        display_usage()
        exit(0)

    global WARNING_ENABLE
    global STRICT_ASSERTS
    global ERRORS_AT_EXIT

    input_file = None

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

    assert input_file is not None, ERROR_FORMAT('USAGE', 'input', 'input was not provided')

    file_content = get_file_content(input_file)

    lexed_file: list[Sentence] = []

    for ln, line in enumerate(file_content):
        line_words = line.split(' ')
        lexed_file.append(lex_line(ln, line_words))

from sys import argv

if __name__ == '__main__':
    try:
        main(len(argv), argv)
    except AssertionError as ass:
        print(ass)
    exit(EXIT_CODE) # END