from sys import exit
from scripts import *

TAB_SIZE = 4

def get_file_content(file_path: str):
    try:
        with open(file_path, 'r') as file:
            lines = file.readlines()
            result: list[tuple[int, str]] = []
            for line in lines:
                line = line.replace(' ' * TAB_SIZE, '\t')
                # strip left
                indent = 0
                for i, ch in enumerate(line):
                    if not ch.isspace():
                        indent = line[:i].count('\t')
                        break
                result.append((indent, line.strip()))
            return result
    except FileNotFoundError:
        return None

def display_help():

    print("USAGE:")
    print("    powang <input.po> [options]  :  Interprets an input.\n")
    print("OPTIONS:")
    print("    --help                :  Displays this message (same as no input).")
    print("    --warn                :  Displays all the warnings.")
    print("    --flex[:option]       :  Flex instructions doesn't panic execution.")
    print("    | discreet            :  Errors at exit doesn't display.")
    print()

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
                set_flag_flex_true()
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
    assert file_content is not None, "File doens't exists: " + input_file

    token_program: list[tuple[int, list[Token]]] = []

    for ln, composed_line in enumerate(file_content):
        indent, line = composed_line
        line_words = line.split()
        token_program.append((indent, tokenize_line(ln, line_words)))

    interpret_program(token_program)

from sys import argv

if __name__ == "__main__":
    try:
        main(len(argv), argv)
    except AssertionError as ass:
        print("\npowang:", ass)
        EXIT_CODE = 1

    if not FLAG_DISCREET and ERRORS_LIST:
        for error_msg in ERRORS_LIST:
            print("\npowang: [FLEX]", error_msg)
    exit(EXIT_CODE) # END