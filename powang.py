from sys import exit
from scripts import *

FLAG_WARNING : bool = False
FLAG_FLEX    : bool = False
FLAG_DISCREET: bool = False

ERRORS_LIST: list[str] = []

EXIT_CODE  : int       = 0
RUNNING    : bool      = True

def interpret_line(ln: int, sentence: list[Token]):
    """### RECURSIVE"""
    
    for tk in sentence:
        if tk.type == TokenType.EXPRESSION:
            return interpret_line(ln, tk.value)

    inst, rest = sentence[0], sentence[1:]

    assert inst.type == TokenType.KEYWORD, error_with_line(ln,
        error_syntax("expecting valid instruction", [f"guilty -> {inst}"]))
    
    assert inst.type == TokenType.KEYWORD, error_with_line(ln,
        error_syntax("expecting valid instruction", [f"guilty -> {inst}"]))

    argc, is_flex, func = INSTRUCTIONS[inst.value]

    print(inst, rest, argc, is_flex, func)

    assert (arg_count := len(rest)) <= argc or argc == -1, error_with_line(ln,
        error_argc(STACK[-1], f'not enough arguments for inst "{inst.value}"', argc, arg_count))
    
    try:
        return func(*rest)
    except AssertionError as ass:
        error = error_with_line(ln, ass.args[0])
        assert FLAG_FLEX and is_flex, error # NORMAL ASSERT
        if not FLAG_DISCREET:
            ERRORS_LIST.append(error)
        return None

def interpret_program(token_program: list[list[Token]]):
    global EXIT_CODE
    for ln, sentence in enumerate(token_program):
        if len(sentence) == 0: # IGNORE EMPTY LINES
            continue

        exit_code_value = interpret_line(ln, sentence)
        # print(exit_code_value)
        if isinstance(exit_code_value, (int, float)):
            EXIT_CODE = int(exit_code_value) # type: ignore

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

    file_content = get_file_content(input_file)

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
        print("\npowang: ", ass)
    exit(EXIT_CODE) # END
    
# TODO: Change the "scope" thing...