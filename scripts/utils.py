def get_file_content(file_path: str):
    with open(file_path, 'r') as file:
        return [line.strip() for line in file.readlines()]

def display_usage():
    print('USAGE:')
    print('    polang <input.po> [options]  :  Interprets an input.\n')
    print('OPTIONS:')
    print('    --strict  :  Terminates the execution when an error is encounter.')
    print('    --warn    :  Displays all the warnings at the end of the execution.')
    print('    --error   :  Shows all the errors at the end of the execution.\n')