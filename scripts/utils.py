def get_file_content(file_path: str):
    with open(file_path, 'r') as file:
        return [line.strip() for line in file.readlines()]

def display_help():
    print("USAGE:")
    print("    polang <input.po> [options]  :  Interprets an input.\n")
    print("OPTIONS:")
    print("    --help                :  Displays this message (same as no input).")
    print("    --warn                :  Displays all the warnings.")
    print("    --flex[:option]       :  Flex instructions doesn't panic execution.")
    print("    | discreet            :  Errors at exit doesn't display.")