from sys import exit
from scripts import *

FLAG_WARNING : bool = False
FLAG_FLEX    : bool = False
FLAG_DISCREET: bool = False

ERRORS_LIST: list[str] = []

EXIT_CODE  : int       = 0

def interpret_line(ln: int, sentence: list[Token]) -> PolangAny:
    """### RECURSIVE"""
    #ic(ln, sentence, '\n')

    inst, rest = sentence[0], sentence[1:]

    assert inst.type == TokenType.KEYWORD, error_with_line(ln,
        error_syntax("expecting valid instruction", [f"guilty -> {inst}"]))

    argc, func_is_flex, func = INSTRUCTIONS[inst.value]

    def process_values(ln: int, rest: list[Token]) -> list[PolangAny]:
        """### RECURSIVE CHILD"""
        value_list: list[PolangAny] = []
        for tk in rest:
            if tk.type == TokenType.NUMBER_LIT or tk.type == TokenType.STRING_LIT:
                value_list.append(tk.value)
            elif tk.type == TokenType.LIST_LIT:
                value_list.append(
                    PolangList(process_values(ln, tk.value), const=False)
                )
            elif tk.type == TokenType.IDENTIFIER:
                assert (value := get_memory(tk.value)) is not None, error_with_line(ln,
                    error_identifier(STACK[-1], tk.value)
                )
                value_list.append(value)
            elif tk.type == TokenType.EXPRESSION:
                value_list.append(interpret_line(ln, tk.value))
        return value_list

    arguments = process_values(ln, rest)

    result = func(*arguments)
    if result.type == 'error':
        assert func_is_flex and FLAG_FLEX, result.data
        ERRORS_LIST.append(result.data)
        return PolangNov()
    else:
        return result

def interpret_program(token_program: list[list[Token]]):
    global EXIT_CODE
    for ln, sentence in enumerate(token_program):
        if len(STACK) == 0:
            return

        if len(sentence) == 0: # IGNORE EMPTY LINES
            continue

        try:
            return_value = interpret_line(ln, sentence)
            if return_value.type == 'number':
                EXIT_CODE = int(return_value.data)
        except AssertionError as ass:
            if not FLAG_DISCREET:
                ERRORS_LIST.append(*ass.args)

def main(argc: int, argv: list[str]):
    if argc == 1:
        display_help()
        exit(0)

    global FLAG_WARNING
    global FLAG_FLEX
    global FLAG_DISCREET
    global ERRORS_LIST
    global EXIT_CODE

    input_file = None

    # Flag and files loop
    for arg in argv[1:]:
        if arg.startswith("--"):
            flag = arg[2:]
            option = None

            # FLAG TRIGGERS

            if ":" in flag:
                flag, option = flag.split(":")

            if flag == "help":
                display_help()
                return
            elif flag == "warn":
                FLAG_WARNING = True
                assert option is None, error_usage("warn does not has options")
            elif flag == "flex":
                FLAG_FLEX = True
                if option is not None:
                    if option == "discreet":
                        FLAG_DISCREET = True
                    else:
                        error_usage("Invalid flag option", [f"option -> {flag}\n    Expected: discreet"])
            else:
                raise_error(error_usage(f"Invalid flag", [f"flag -> {flag}"]))
        else:
            assert input_file is None, error_usage("input already provided", [f"input -> {input_file}"])
            input_file = arg

    # File doesn"t exist ERROR
    if input_file is None:
        print(error_usage("input was not provided"))
        display_help()
        EXIT_CODE = 1
        return

    file_content: list[str] | None = get_file_content(input_file)
    assert file_content is not None, "File doens't exists: " + input_file

    token_program: list[list[Token]] = []

    for ln, line in enumerate(file_content):
        line_words = line.split(" ")
        token_program.append(tokenize_line(ln, line_words))

    interpret_program(token_program)

from sys import argv

if __name__ == "__main__":
    try:
        main(len(argv), argv)
        if ERRORS_LIST:
            for error_msg in ERRORS_LIST:
                print("\npowang: [FLEX]", error_msg)
    except AssertionError as ass:
        print("\npowang:", ass)
        exit(1)
    exit(EXIT_CODE) # END

# TODO:
# - Change the "scope" thing... (whatever this means...).
# - Add the TokenNumberValue