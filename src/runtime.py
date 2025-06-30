from re import match
from .parser import *
from .error import *

from .builtins.stdout import *
from .builtins.stdin import *
from .builtins.info import *

from .builtins.cast import * # HELPER

CallableFormat = tuple[int, int, Callable[(...), PowangAny]]

BUILTINS: dict[str, CallableFormat] = {
    'stdout': (1, -1, builtin_stdout),
    'stdin' : (0, 1 , builtin_stdin ),
    'print' : (0,  3, builtin_print ),
    'stdfmt': (1, -1, builtin_stdfmt),
    'size'  : (1, -1, builtin_size  ),
    'typeof': (1, 1, builtin_typeof ),
}

memory: dict[str, PowangAny] = {}

def helper_check_types(where: str, type: str, value: PowangAny) -> PowangAny:
    if type != value.type:
        assert (casted := PowangCast(type, value)) is not None, powang_error_type_match(
            where,
            type,
            value.type
        )
        return PowangCopyConstruct(casted)
    return PowangCopyConstruct(value)

def parseIndexExpression(where: str, expression: DictRepr, subscript_check: bool):
    target_value = evaluate_ast_expression(expression['value']['target'])
    assert target_value.defined, powang_error_undefined_reference(
        TokenToString(ParserTokenType.ASSIGNMENT),
        expression['value']['target']['value']
    )
    
    index = evaluate_ast_expression(expression['value']['index'])
    
    if subscript_check:
        assert target_value.type == PowangString.type, powang_error_format("ASSIGN", where, "string type is not subscriptable for now.")
    if target_value.type == PowangArray.type:
        assert index.type == PowangInteger.type, powang_error_format(
            'INDEX', where, f"{PowangArray.type} indeces must be {PowangInteger.type}", [
                f"index value is {index.type}"
            ])
        assert index.data >= 0 and index.data < len(target_value.data), powang_error_index_out_of_range(index.data, len(target_value.data))
        return target_value.data[index.data]
    elif target_value.type == PowangString.type:
        assert index.type == PowangInteger.type, powang_error_type_match(
            TokenToString(ParserTokenType.INDEX_EXPRESSION),
            PowangInteger.type,
            index.type,
        )
        assert index.data >= 0 and index.data < len(target_value.data), powang_error_index_out_of_range(index.data, len(target_value.data))
        return PowangString(target_value.data[index.data])
    elif target_value.type == PowangMap.type:
        assert (value := target_value.data.get(index)) is not None, powang_error_format(
            "KEY", where, f"Doesn't exists: {index}"
        )
        return value
    elif target_value.type == PowangUserType.type:
        assert 'operator[]' in target_value.methods, powang_error_format(
            'INDEX', where, f"Type {target_value.name} has no access operator []"
        )
        # TODO: Add the method calls
        return None
    return target_value

def evaluate_ast_expression(expression: DictRepr) -> PowangAny:
    if expression == {}:
        return PowangNova()

    from icecream import ic

    where = TokenToString(expression['type'])
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

        case LexerTokenType.IDENTIFIER:
            assert (value := memory.get(expression['value'])) is not None, \
                powang_error_identifier_not_found(None, expression['value'])
            return value

        case ParserTokenType.UNARY_EXPRESSION:
            operator = expression['value']['operator']['value']
            right = evaluate_ast_expression(expression['value']['right'])

            match operator:
                case '!':
                    return PowangBoolean(not PowangBoolean.cast(right).data)
                case '+':
                    if right.type == PowangArray.type:
                        result: PowangAny = right.data[0]
                        for element in right.data[1:]:
                            result += element
                        return result
                    return right
                case '-':
                    if right.type == PowangInteger.type:
                        return PowangInteger(-right.data)
                    if right.type == PowangNumber.type:
                        return PowangNumber(-right.data)
                    if right.type == PowangString.type:
                        return PowangString(right.data[::-1])
                    if right.type == PowangArray.type:
                        return PowangArray(right.data[::-1])
                    else:
                        powang_throw(powang_error_invalid_type_for_prefix_operator(None, operator, right.type))
            powang_throw(powang_error_prefix_operator(None, operator))

        case ParserTokenType.BINARY_EXPRESSION:
            left = evaluate_ast_expression(expression['value']['left'])
            operator = expression['value']['operator']['value']
            if operator == 'as':
                right = expression['value']['right']['value']
                assert right in TYPES, powang_error_identifier_type(where, right)
                # EXPLICIT CASTING
                assert (casted := explicit_cast(right, left)) is not None, powang_error_format_invalid_cast(
                    None,
                    right,
                    left.type,
                    True,
                )
                
                value = PowangCopyConstruct(casted)
                return value

            right = evaluate_ast_expression(expression['value']['right'])
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
            identifier: str = expression['value']['identifier']['value']
            
            assert identifier not in memory, powang_error_format('REDEFINE', where, "Cannot redefine variables", [
                f"redefined: {identifier}"
            ])
            
            type: DictRepr = expression['value']['type']['value']
            assert type['value'] in TYPES, powang_error_identifier_type(where, type['value'])


            value = evaluate_ast_expression(expression['value']['expression'])
            assert value.defined, powang_error_undefined_reference(
                where,
                identifier,
            )

            if not (weak := type['weak']) and not value.weak.has_value:
                raise powang_throw(powang_error_strong_nova_assign(
                    where,
                    identifier,
                ))
            elif not value.weak.has_value:
                right_value                = PowangTypeMap(type['value'])()
                right_value.weak.has_value = False  
                if type['const']:
                    right_value.const.can_change = True
            elif type['value'] == PowangSome.type:
                right_value      = PowangSome(PowangCopyConstruct(value).data)
                right_value.some = value.type
            else:
                right_value = helper_check_types(where, type['value'], value)

            right_value.weak._it_is  = weak
            right_value.const._it_is = type['const']
            memory[identifier]      = right_value
            return right_value

        case ParserTokenType.DECLARATION_INTERPRET:
            identifier = expression['value']['identifier']['value']
            assert identifier not in memory, powang_error_format('REDEFINE', where, "Cannot redefine variables", [
                f"redefined: {identifier}"
            ])
            value = evaluate_ast_expression(expression['value']['expression'])
            right_value = PowangCopyConstruct(value)
            memory[identifier] = right_value
            return right_value

        case ParserTokenType.DECLARATION_UNDEFINED:
            identifier = expression['value']['identifier']['value']
            assert identifier not in memory, powang_error_format('REDEFINE', where, "Cannot redefine variables", [
                f"redefined: {identifier}"
            ])
            
            type = expression['value']['type']['value']
            assert type['value'] in TYPES, powang_error_identifier_type(where, type['value'])
            
            right_default = PowangTypeMap(type['value'])()
            right_default.defined = False
            right_default.weak._it_is = type['weak']
            right_default.weak.has_value = False
            right_default.const._it_is = type['const']
            right_default.const.can_change = type['weak']
            
            memory[identifier] = right_default
            return right_default

        case ParserTokenType.ASSIGNMENT:
            target = expression['value']['target']

            if target['type'] == ParserTokenType.INDEX_EXPRESSION:
                target_value = parseIndexExpression(where, target, True)
                assert target_value is not None, powang_error_format(
                    'IMPLEMENTATION', where, "Index to that type is not implemented yet."
                )
            else:
                assert (target_value := memory.get(target['value'])) is not None, powang_error_identifier_not_found(
                    where,
                    target['value'],
                )

            value = evaluate_ast_expression(expression['value']['expression'])

            if target_value.const:
                assert not target_value.defined or target_value.const.can_change, powang_error_format(
                    "CONST", where, "Trying to assign to a strong const", [
                        f"{value} -> {target_value}"
                    ])
                target_value.const.can_change = False

            if not target_value.weak and not value.weak.has_value:
                raise powang_throw(powang_error_strong_nova_assign(
                    where,
                    target['value'],
                ))
            elif not value.weak.has_value:
                target_value.weak.has_value = False  
                target_value.data = PowangTypeMap(target_value.type)().data # type: ignore
            elif target_value.type == PowangSome.type:
                target_value.data = PowangCopyConstruct(value).data
                target_value.some = value.type
                target_value.weak.has_value = True
            else:
                target_value.data = helper_check_types(where, target_value.type, value).data # type: ignore
                target_value.weak.has_value = True
            target_value.defined = True
            return target_value

        case ParserTokenType.ARRAY_EXPRESSION:
            expr_elements = expression['value']['elements']
            if expression['value']['type'] == PowangMap.type:
                return PowangMap({
                    evaluate_ast_expression(key_value['value']['key']):
                    evaluate_ast_expression(key_value['value']['value'])
                    for key_value in expr_elements
                })
            elements: list = [evaluate_ast_expression(item) for item in expression['value']['elements']]
            return PowangArray(elements)
        
        case ParserTokenType.INDEX_EXPRESSION:
            index_expression_value = parseIndexExpression(where, expression, False)
            assert index_expression_value is not None, powang_error_format(
                'IMPLEMENTATION', where, "Index to that type is not implemented yet."
            )
            return index_expression_value

        case ParserTokenType.CALL_EXPRESSION:
            callee = expression['value']['callee']['value']
            args = [evaluate_ast_expression(arg) for arg in expression['value']['arguments']]
            
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
        result = evaluate_ast_expression(statement)
    return result