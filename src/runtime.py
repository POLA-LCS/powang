from re import match
from .parser import *
from .error import *

from .builtins.stdout import *
from .builtins.stdin import *
from .builtins.size import *

CallableFormat = tuple[int, int, Callable[(...), PowangAny]]

BUILTINS: dict[str, CallableFormat] = {
    'stdout': (1, -1, builtin_stdout),
    'stdin' : (1, 1 , builtin_stdin ),
    'print' : (0,  3, builtin_print ),
    'size'  : (1, -1, builtin_size  ),
}

memory: dict[str, PowangAny] = {}

def helper_check_types(type: str, value: PowangAny) -> PowangAny:
    if type != value.type:
        assert (casted := PowangCast(type, value)) is not None, powang_error_type_match(
            "Variable definition",
            type,
            value.type
        )
        value = PowangCopyConstruct(casted)
    return value

def evaluate_expression(expression: DictRepr, identifier: bool = False) -> PowangAny:
    if expression == {}:
        return PowangNova()

    def format_string(string: str):
        pattern = r'$\{([^\']*)\}'
        encounter = ''
        encounter = match(pattern, string)
        if encounter is not None:
            parsed = Parser(encounter.string[2:-1] + ';').parse()
            result = evaluate_expression(parsed[0])
            string = string.replace(encounter.string, f"{result.data}")
        return string

    match expression['type']:
        case LexerTokenType.NOVA_LITERAL:
            return PowangNova()

        case LexerTokenType.BOOLEAN_LITERAL:
            return PowangBoolean(expression['value'])
        
        case LexerTokenType.INTEGER_LITERAL:
            return PowangInteger(int(expression['value']))

        case LexerTokenType.FLOATING_LITERAL:
            return PowangNumber(float(expression['value']))

        case LexerTokenType.STRING_LITERAL:
            return PowangString(expression['value'])

        case LexerTokenType.FMT_STRING_LITERAL:
            string = format_string(expression['value'])
            return PowangString(string)

        case LexerTokenType.IDENTIFIER:
            assert (value := memory.get(expression['value'])) is not None, \
                powang_error_identifier_not_found(None, expression['value'])
            return value

        case ParserTokenType.BINARY_EXPRESSION:
            left = evaluate_expression(expression['value']['left'])
            right = evaluate_expression(expression['value']['right'])

            match expression['value']['operator']['value']:
                case '+':
                    return left + right
                case '-':
                    return left - right
                case '*':
                    return left * right
                case '/':
                    return left / right
                case _:
                    raise ValueError(f"Unknown operator: {expression['operator']}")

        case ParserTokenType.DECLARATION_TYPED_VAR:
            name = expression['value']['identifier']['value']
            type = expression['value']['type']['value']
            assert type['value'] in TYPES, powang_error_identifier_type(TokenToString(expression['type']), type)

            value = evaluate_expression(expression['value']['expression'])
            assert value.defined, powang_error_undefined_value(
                TokenToString(expression['type']),
                name,
                expression['value']['expression']['value'],
            )
            
            if value.type == PowangNova.type:
                assert type['weak'], powang_error_strong_nova_assign(None, name)
                right_value = value
            else:
                right_value = helper_check_types(type['value'], value)
            right_value.weak = type['weak']
            right_value.defined = True
            memory[name] = right_value
            return right_value

        case ParserTokenType.DECLARATION_INTERPRET:
            name = expression['value']['identifier']['value']
            value = evaluate_expression(expression['value']['expression'])
            right_value = PowangCopyConstruct(value)
            memory[name] = right_value
            return value

        case ParserTokenType.DECLARATION_UNDEFINED:
            name = expression['value']['identifier']['value']
            type = expression['value']['type']['value']
            assert type['value'] in TYPES, powang_error_identifier_type(TokenToString(expression['type']), type)
            value = PowangTypeMap(type['value'])(properties={'defined': False})
            if value.type == PowangNova.type:
                assert type['weak'], powang_error_strong_nova_assign(None, name)
                right_value = value
                right_value.defined = False
            else:
                right_value = helper_check_types(type['value'], value)
            if type['weak']:
                right_value.weak = True
            memory[name] = right_value
            return value

        case ParserTokenType.ASSIGNMENT:
            name = expression['value']['identifier']['value']
            assert (left_value := memory.get(name)) is not None, powang_error_identifier_not_found(
                TokenToString(expression['type']),
                name,
            )
            value = evaluate_expression(expression['value']['expression'])
            if value.type == PowangNova.type:
                assert left_value.weak, powang_error_strong_nova_assign(None, name)
                left_value.data = value.data # type: ignore
                left_value.nova = True
            else:
                right_value = helper_check_types(left_value.type, value)
                left_value.data = right_value.data # type: ignore
                left_value.nova = False
            left_value.defined = True
            return left_value

        case ParserTokenType.LIST_EXPRESSION:
            elements: list = [evaluate_expression(item) for item in expression['value']]
            return PowangContainer(elements)

        case ParserTokenType.CALL_EXPRESSION:
            callee = expression['value']['callee']['value']
            args = [evaluate_expression(arg) for arg in expression['value']['arguments']]
            if callee in BUILTINS:
                min_argc, max_argc, func = BUILTINS[callee]
                if max_argc != -1:
                    assert len(args) <= max_argc, powang_error_format("ARGUMENT", 'Function call', 'too many arguments')
                assert len(args) >= min_argc, powang_error_format("ARGUMENT", 'Function call', 'not enought arguments')
                return func(*args)
            for i, arg in enumerate(args):
                assert arg.defined, powang_error_undefined_argument(callee, i + 1, arg.type,)
            raise ValueError(f"Unknown function: {callee}")

    return PowangNova()

def interpret_program(program: list[DictRepr]):
    result = PowangNova()
    for statement in program:
        result = evaluate_expression(statement)
    return result