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

Memory = dict[str, PowangAny]
scope_stack: list[Memory] = [{}]

def exists_in_memory(name: str):
    global scope_stack
    for scope in scope_stack[::-1]:
        if (value := scope.get(name)) is not None:
            return value
    return None

def pop_stack():
    global scope_stack
    scope_stack.pop()
    return True

def new_scope():
    global scope_stack
    scope_stack.append({})
    return True
    
def isolate_process(process: DictRepr):
    new_scope()
    evaluate_ast_expression(process)
    pop_stack()
    return True

def perform_operation(operator: str, left: PowangAny, right: PowangAny) -> PowangAny:
    result: PowangAny | None = None
    match operator:
        case '+': result = left + right
        case '-': result = left - right
        case '*': result = left * right
        case '/': result = left / right
    if result is None:
        casted = PowangCast(left.type, right)
        assert casted is not None, powang_error_unsupported_operation('implicit operation', left.type, operator, right.type)
        return perform_operation(operator, left, casted)
    return result

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
        assert target_value.type != PowangString.type, powang_error_format("ASSIGN", where, "string type is not subscriptable for now.")
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
            assert (value := exists_in_memory(expression['value'])) is not None, \
                powang_error_identifier_not_found(None, expression['value'])
            return value

        case ParserTokenType.UNARY_EXPRESSION:
            operator = expression['value']['operator']['value']
            right = evaluate_ast_expression(expression['value']['right'])

            match operator:
                case '!':
                    return PowangBoolean(not PowangBoolean.cast(right).data)
                case '[-]':
                    if right.type == PowangInteger.type:
                        return explicit_cast_integer(PowangString(explicit_cast_string(right).data[::-1])) # type: ignore
                    if right.type == PowangNumber.type:
                        return explicit_cast_number(PowangString(explicit_cast_string(right).data[::-1])) # type: ignore
                    if right.type == PowangString.type:
                        return PowangString(right.data[::-1])
                    if right.type == PowangArray.type:
                        return PowangArray(right.data[::-1])
                case '-':
                    if right.type == PowangInteger.type:
                        return PowangInteger(-right.data)
                    if right.type == PowangNumber.type:
                        return PowangNumber(-right.data)
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
            operator = expression['value']['operator']['value']
            return perform_operation(operator, left, right)
        
        case ParserTokenType.DECLARATION_TYPED_VAR:
            identifier: str = expression['value']['identifier']['value']
            
            assert identifier not in scope_stack[-1], powang_error_format('REDEFINE', where, "Cannot redefine variables", [
                f"redefined: {identifier}"
            ])
            
            type: DictRepr = expression['value']['type']['value']
            assert type['value'] in TYPES, powang_error_identifier_type(where, type['value'])

            value = evaluate_ast_expression(expression['value']['expression'])
            assert value.defined, powang_error_undefined_reference(
                where,
                identifier,
            )

            weak = PowangType_Base.PropertyWeak(type['weak'], value.weak.has_value)
            const = PowangType_Base.PropertyConst(type['const'], type['weak'] and not value.weak.has_value)
            if weak:
                right_value = PowangTypeMap(type['value'])()
            elif type['value'] == PowangSome.type:
                right_value = PowangSome(value.data)
                right_value.some = value.type
            else:
                right_value = helper_check_types(where, type['value'], value)
            right_value.weak   = weak
            right_value.const  = const
            scope_stack[-1][identifier] = right_value
            return right_value

        case ParserTokenType.DECLARATION_INTERPRET:
            identifier = expression['value']['identifier']['value']
            assert identifier not in scope_stack[-1], powang_error_format('REDEFINE', where, "Cannot redefine variables", [
                f"redefined: {identifier}"
            ])
            value = evaluate_ast_expression(expression['value']['expression'])
            
            if value.type == PowangSome.type:
                right_value = PowangTypeMap(value.some)(value.data)
            else:
                right_value = PowangCopyConstruct(value)

            scope_stack[-1][identifier] = right_value
            return right_value            

        case ParserTokenType.DECLARATION_UNDEFINED:
            identifier = expression['value']['identifier']['value']
            assert identifier not in scope_stack[-1], powang_error_format('REDEFINE', where, "Cannot redefine variables", [
                f"redefined: {identifier}"
            ])
            
            type = expression['value']['type']['value']
            assert type['value'] in TYPES, powang_error_identifier_type(where, type['value'])
            
            weak = PowangType_Base.PropertyWeak(type['weak'], False)
            const = PowangType_Base.PropertyConst(type['const'], True)
            right_value = PowangTypeMap(type['value'])()
            right_value.weak   = weak
            right_value.const  = const
            right_value.defined = False
            scope_stack[-1][identifier] = right_value
            return right_value

        case ParserTokenType.ASSIGNMENT:
            target = expression['value']['target']

            if target['type'] == ParserTokenType.INDEX_EXPRESSION:
                target_value = parseIndexExpression(where, target, True)
                assert target_value is not None, powang_error_format(
                    'IMPLEMENTATION', where, "Index to that type is not implemented yet."
                )
            else:
                assert (target_value := exists_in_memory(target['value'])) is not None, powang_error_identifier_not_found(
                    where,
                    target['value'],
                )

            value = evaluate_ast_expression(expression['value']['expression'])

            if target_value.const:
                assert not target_value.defined or target_value.const.can_change, powang_error_format(
                    "CONST", where, "Trying to assign to a strong const", [
                        f"{value.type} -> {target_value.type}!"
                    ])
                target_value.const.can_change = False

            if not value.weak.has_value:
                assert target_value.weak or target_value.type == PowangNova.type, powang_throw(powang_error_strong_nova_assign(
                    where,
                    target['value'],
                ))
            elif target_value.type == PowangSome.type:
                target_value.data = PowangCopyConstruct(value).data
                target_value.some = value.type
            else:
                target_value.data = helper_check_types(where, target_value.type, value).data # type: ignore
            target_value.defined = True
            target_value.weak.has_value = value.weak.has_value
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

        case ParserTokenType.IF_STATEMENT:
            new_scope()
            expr = expression['value']['expression']
            block = expression['value']['block']
            else_block = expression['value']['else']
            
            if new_scope() and PowangBoolean.cast(evaluate_ast_expression(expr)).data:
                new_scope()
                for statement in block['value']:
                    evaluate_ast_expression(statement)
                pop_stack()
            elif else_block is not None:
                new_scope()
                for statement in else_block['value']:
                    evaluate_ast_expression(statement)
                pop_stack()
            pop_stack()
            return PowangNova()
                    
        case ParserTokenType.FOR_STATEMENT:
            start_expression = expression['value']['start_expression']
            middle_expression = expression['value']['middle_expression']
            last_expression = expression['value']['last_expression']
            block = expression['value']['block']

            if middle_expression is None:
                middle_expression = start_expression
                start_expression = None
                
            if start_expression is not None:
                evaluate_ast_expression(start_expression)
            while new_scope() and PowangBoolean.cast(evaluate_ast_expression(middle_expression)).data:
                new_scope()
                for statement in block['value']:
                    evaluate_ast_expression(statement)
                pop_stack()
                if last_expression is not None:
                    evaluate_ast_expression(last_expression)
                pop_stack()
            return PowangNova()
        
        case ParserTokenType.FOR_EACH_STATEMENT:
            iterable_expression = expression['value']['expression']

            new_scope()
            iterable = evaluate_ast_expression(iterable_expression)
            assert iterable.type == PowangArray.type, powang_error_format("VALUE", where, "Expression is not an iterable value", [
                f"Expression is of type {iterable.type}"
            ])
            
            iterator_identifier = expression['value']['iterator']
            iterator = evaluate_ast_expression(iterator_identifier)

            block = expression['value']['block']
            for data in iterable.data:
                scope_stack[-1][iterator_identifier['value']['identifier']['value']] = helper_check_types(where, iterator.type, data)
                new_scope()
                for statement in block['value']:
                    evaluate_ast_expression(statement)
                pop_stack()
            pop_stack()
                    
    return PowangNova()

def interpret_program(program: list[DictRepr]):
    result = PowangNova()
    for statement in program:
        result = evaluate_ast_expression(statement)
    return result