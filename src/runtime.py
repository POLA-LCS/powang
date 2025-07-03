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
functions_stack: list[dict[str, PowangFunction]] = [{}]

def exists_in_memory(name: str):
    global scope_stack
    for scope in scope_stack[::-1]:
        if (value := scope.get(name)) is not None:
            return value
    return None

def function_exists_in_memory(name: str) -> PowangFunction | None:
    global functions_stack
    for scope in functions_stack[::-1]:
        if (func := scope.get(name)) is not None:
            return func
    return None

def pop_stack():
    global scope_stack
    scope_stack.pop()
    functions_stack.pop()
    return True

def new_scope():
    global scope_stack
    scope_stack.append({})
    functions_stack.append({})
    return True
    
def assign_variable_with_checks(where: str, target_value: PowangAny, right_value: PowangAny):
    if right_value.type == PowangSome.type:
        right_value = PowangTypeMap(right_value.some)(right_value.data)

    if target_value.const:
        assert not target_value.defined or target_value.const.can_change, powang_error_format(
            "CONST", where, "Trying to assign to a strong const", [
                f"{right_value.type} -> {target_value.type}!"
            ])
        target_value.const.can_change = False

    if not target_value.weak:
        assert right_value.weak.has_value, powang_error_strong_nova_assign(where, target_value.type)

    if target_value.type == PowangSome.type:
        target_value.data = PowangCopyConstruct(right_value).data
        target_value.some = right_value.type
    else:
        target_value.data = helper_check_types(where, target_value.type, right_value, target_value.weak._it_is).data # type: ignore
    target_value.defined = True
    target_value.weak.has_value = right_value.weak.has_value
    return target_value

def perform_operation(operator: str, left: PowangAny, right: PowangAny, typed: bool) -> PowangAny:
    if left.type == PowangSome.type:
        left = PowangTypeMap(left.some)(left.data)
    if right.type == PowangSome.type:
        right = PowangTypeMap(right.some)(right.data)
        
    result: PowangAny | None = None

    match operator:
        case '+' : result = left + right
        case '-' : result = left - right
        case '*' : result = left * right
        case '/' : result = left / right
        case _:
            result = PowangBoolean(False)
            if not left.weak.has_value or not right.weak.has_value:
                assert operator in {'==', '!='}, powang_error_format("VALUE", 'comparisson', "Invalid weak comparisson", [
                    "trying to compare greatness or lessness with non strong values"
                ])
                if operator == '==':
                    return PowangBoolean(left.weak.has_value == right.weak.has_value)
                return PowangBoolean(left.weak.has_value != right.weak.has_value)
            if left.type != right.type:
                if typed:
                    return result
                casted = PowangCast(left.type, right)
                assert casted is not None, powang_error_unsupported_operation('comparisson', left.type, operator, right.type)
                return perform_operation(operator, left, casted, False)
            match operator:
                case '==':
                    result.data = left == right
                case '!=':
                    result.data = left != right
                case '<=':
                    result.data = left < right or left == right
                case '>=':
                    result.data = left > right or left == right
                case '<':
                    result.data = left < right
                case '>':
                    result.data = left > right
            return result

    if result is None:
        if typed:
            casted = PowangCast(right.type, left)
            assert casted is not None, powang_error_unsupported_operation('implicit typed operation', left.type, operator, right.type)
            return perform_operation(operator, casted, right, False)
        else:
            casted = PowangCast(left.type, right)
            assert casted is not None, powang_error_unsupported_operation('implicit operation', left.type, operator, right.type)
        return perform_operation(operator, left, casted, typed)
    
    return result

def helper_check_types(where: str, type: str, value: PowangAny, weak: bool = False) -> PowangAny:
    if not weak:
        assert value.weak.has_value, powang_error_strong_nova_assign(
            where,
            type,
        )
    elif not value.weak.has_value:
        return PowangNova()
    if type != PowangSome.type and type != value.type:
        assert (casted := PowangCast(type, value)) is not None, powang_error_type_match(
            where,
            type,
            value.type
        )
        return PowangCopyConstruct(casted)
    return PowangCopyConstruct(value)

def parseIndexExpression(where: str, expression: DictRepr, subscript_check: bool):
    target_value = evaluate_ast_expression(expression['target'])
    assert target_value.defined, powang_error_undefined_reference(
        TokenToString(ParserTokenType.ASSIGNMENT),
        expression['target']['value']
    )
    
    if target_value.type == PowangSome.type:
        target_value = PowangTypeMap(target_value.some)(target_value.data)
    
    index = evaluate_ast_expression(expression['index'])
    
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

def check_identifier(where: str, identifier: DictRepr) -> str:
    identifier_name = evaluate_ast_expression(identifier, True)
    assert isinstance(identifier_name, str), powang_error_syntax_unexpected_token(
        where, identifier_name.type, TokenToString(LexerTokenType.IDENTIFIER)
    )
    return identifier_name
    
def evaluate_ast_expression(expression: DictRepr, is_identifier: bool = False) -> PowangAny:
    if expression == {}:
        return PowangNova()

    from icecream import ic

    where = TokenToString(expression['type'])
    expr_value = expression['value']
    match expression['type']:
        case LexerTokenType.IDENTIFIER:
            if expr_value == 'nova':
                return PowangNova()
            if expr_value in {'true', 'false'}:
                return PowangBoolean(expr_value == 'true')
            if is_identifier:
                return expr_value
            assert (identifier_value := exists_in_memory(expr_value)) is not None, \
                powang_error_identifier_not_found(None, expr_value)
            return identifier_value

        case LexerTokenType.INTEGER_LITERAL:
            return PowangInteger(int(expr_value))

        case LexerTokenType.FLOATING_LITERAL:
            return PowangNumber(float(expr_value))

        case LexerTokenType.STRING_LITERAL:
            return PowangString(expr_value)

        case ParserTokenType.UNARY_EXPRESSION:
            unary_operator = expr_value['operator']['value']
            unary_right = evaluate_ast_expression(expr_value['right'])

            match unary_operator:
                case '!':
                    return PowangBoolean(not PowangBoolean.cast(unary_right).data)
                case '[-]':
                    if unary_right.type == PowangInteger.type:
                        return explicit_cast_integer(PowangString(explicit_cast_string(unary_right).data[::-1])) # type: ignore
                    if unary_right.type == PowangNumber.type:
                        return explicit_cast_number(PowangString(explicit_cast_string(unary_right).data[::-1])) # type: ignore
                    if unary_right.type == PowangString.type:
                        return PowangString(unary_right.data[::-1])
                    if unary_right.type == PowangArray.type:
                        return PowangArray(unary_right.data[::-1])
                case '-':
                    if unary_right.type == PowangInteger.type:
                        return PowangInteger(-unary_right.data)
                    if unary_right.type == PowangNumber.type:
                        return PowangNumber(-unary_right.data)
                    else:
                        powang_throw(powang_error_invalid_type_for_prefix_operator(None, unary_operator, unary_right.type))
            powang_throw(powang_error_prefix_operator(None, unary_operator))

        case ParserTokenType.BINARY_EXPRESSION:
            binary_left = evaluate_ast_expression(expr_value['left'])
            if binary_left.type == PowangSome.type:
                binary_left = PowangTypeMap(binary_left.some)(binary_left.data)
            binary_operator = expr_value['operator']['value']
            binary_right = expr_value['right']['value']
            if binary_operator == 'as':
                assert binary_right in TYPES, powang_error_identifier_type(where, binary_right)

                # EXPLICIT CASTING
                assert (binary_casted := explicit_cast(binary_right, binary_left)) is not None, powang_error_format_invalid_cast(
                    None,
                    binary_right,
                    binary_left.type,
                    True,
                )
                binary_value = PowangCopyConstruct(binary_casted)
                return binary_value
            elif binary_operator in {'::', '!:'}:
                if binary_right not in TYPES:
                    binary_right = evaluate_ast_expression(expr_value['right']).type
                match binary_operator:
                    case '::':
                        return PowangBoolean(binary_left.type == binary_right)
                    case '!:':
                        return PowangBoolean(binary_left.type != binary_right)
            elif binary_operator == '&&':
                if not PowangBoolean.cast(binary_left).data:
                    return PowangBoolean(False)
                return PowangBoolean.cast(evaluate_ast_expression(expr_value['right']))
            elif binary_operator == '||':
                if PowangBoolean.cast(binary_left).data:
                    return PowangBoolean(True)
                return PowangBoolean.cast(evaluate_ast_expression(expr_value['right']))

            binary_right = evaluate_ast_expression(expr_value['right'])
            binary_operator = expr_value['operator']['value']
            return perform_operation(binary_operator, binary_left, binary_right, expr_value['typed'])
        
        case ParserTokenType.DECLARATION_TYPED_VAR:
            typed_identifier = check_identifier(where, expr_value['identifier'])
            
            assert scope_stack[-1].get(typed_identifier) is None, powang_error_format('REDEFINE', where, "Cannot redefine variables", [
                f"redefined: {typed_identifier}"
            ])
            
            typed_type: DictRepr = expr_value['type']['value']
            assert typed_type['value'] in TYPES, powang_error_identifier_type(where, typed_type['value'])

            typed_value = evaluate_ast_expression(expr_value['expression'])
            assert typed_value.defined, powang_error_undefined_reference(
                where,
                typed_identifier,
            )
            
            if typed_value.type == PowangSome.type:
                typed_value = PowangTypeMap(typed_value.some)(typed_value.data)
            
            typed_weak  = PowangType_Base.PropertyWeak(typed_type['weak'], typed_value.weak.has_value)
            typed_const = PowangType_Base.PropertyConst(typed_type['const'], typed_type['weak'] and not typed_value.weak.has_value)
            if typed_type['value'] == PowangSome.type:
                typed_right_value = PowangSome(typed_value.data)
                typed_right_value.some = typed_value.type
            else:
                typed_result = helper_check_types(where, typed_type['value'], typed_value, typed_weak._it_is)
                if typed_result.type == PowangNova.type and typed_weak:
                    typed_right_value = PowangTypeMap(typed_type['value'])(typed_value.data)
                else:
                    typed_right_value = typed_result
            typed_right_value.weak  = typed_weak
            typed_right_value.const = typed_const
            scope_stack[-1][typed_identifier] = typed_right_value
            return typed_right_value

        case ParserTokenType.DECLARATION_INTERPRET:
            interpret_identifier = check_identifier(where, expr_value['identifier'])
            assert interpret_identifier not in scope_stack[-1], powang_error_format('REDEFINE', where, "Cannot redefine variables", [
                f"redefined: {interpret_identifier}"
            ])
            interpret_value = evaluate_ast_expression(expr_value['expression'])
            
            if interpret_value.type == PowangSome.type:
                interpret_right_value = PowangTypeMap(interpret_value.some)(interpret_value.data)
            else:
                interpret_right_value = PowangCopyConstruct(interpret_value)

            scope_stack[-1][interpret_identifier] = interpret_right_value
            return interpret_right_value            

        case ParserTokenType.DECLARATION_UNDEFINED:
            undefined_identifier = check_identifier(where, expr_value['identifier'])
            assert undefined_identifier not in scope_stack[-1], powang_error_format('REDEFINE', where, "Cannot redefine variables", [
                f"redefined: {undefined_identifier}"
            ])
            
            undefined_type = expr_value['type']['value']
            assert undefined_type['value'] in TYPES, powang_error_identifier_type(where, undefined_type['value'])
            
            undefined_weak = PowangType_Base.PropertyWeak(undefined_type['weak'], False)
            undefined_const = PowangType_Base.PropertyConst(undefined_type['const'], True)
            undefined_right_value = PowangTypeMap(undefined_type['value'])()
            undefined_right_value.weak   = undefined_weak
            undefined_right_value.const  = undefined_const
            undefined_right_value.defined = False
            scope_stack[-1][undefined_identifier] = undefined_right_value
            return undefined_right_value

        case ParserTokenType.ASSIGNMENT:
            assign_target = expr_value['target']

            if assign_target['type'] == ParserTokenType.INDEX_EXPRESSION:
                assign_target_value = parseIndexExpression(where, assign_target, True)
                assert assign_target_value is not None, powang_error_format(
                    'IMPLEMENTATION', where, "Index to that type is not implemented yet."
                )
            else:
                assign_target = check_identifier(where, assign_target)
                assert (assign_target_value := exists_in_memory(assign_target)) is not None, powang_error_identifier_not_found(
                    where,
                    assign_target,
                )

            assign_value = evaluate_ast_expression(expr_value['expression'])
            assign_variable_with_checks(where, assign_target_value, assign_value)

        case ParserTokenType.ARRAY_EXPRESSION:
            array_expr_elements = expr_value['elements']
            if expr_value['type'] == PowangMap.type:
                return PowangMap({
                    evaluate_ast_expression(key_value['value']['key']):
                    evaluate_ast_expression(key_value['value']['value'])
                    for key_value in array_expr_elements
                })
            array_elements: list = [evaluate_ast_expression(array_item) for array_item in array_expr_elements]
            return PowangArray(array_elements)
        
        case ParserTokenType.INDEX_EXPRESSION:
            index_expression_value = parseIndexExpression(where, expression['value'], False)
            assert index_expression_value is not None, powang_error_format(
                'IMPLEMENTATION', where, "Index to that type is not implemented yet."
            )
            return index_expression_value

        case ParserTokenType.CALL_EXPRESSION:
            call_callee = check_identifier(where, expr_value['callee'])
            call_args = [evaluate_ast_expression(call_arg) for call_arg in expr_value['arguments']]
            
            if call_callee in BUILTINS:
                call_min_argc, call_max_argc, call_func = BUILTINS[call_callee]
                if call_max_argc != -1:
                    assert len(call_args) <= call_max_argc, powang_error_format("ARGUMENT", 'Function call', 'too many arguments')
                assert len(call_args) >= call_min_argc, powang_error_format("ARGUMENT", 'Function call', 'not enought arguments')
                return call_func(*call_args)
            elif (func := function_exists_in_memory(call_callee)) is not None:
                for i, call_arg in enumerate(call_args):
                    assert call_arg.defined, powang_error_undefined_argument(call_callee, i + 1, call_arg.type)
                assert len(call_args) <= len(func.args), powang_error_format("ARGUMENT", 'Function call', 'too many arguments')
                assert len(call_args) >= len(func.args), powang_error_format("ARGUMENT", 'Function call', 'not enought arguments')

                call_return_value: PowangAny = PowangNova()
                new_scope()
                for i, call_arg in enumerate(func.args):
                    call_argument = evaluate_ast_expression(call_arg)
                    assign_variable_with_checks('function call', call_argument, call_args[i])

                new_scope()
                for call_statement in func.code:
                    call_return_value = evaluate_ast_expression(call_statement)
                pop_stack()

                call_final_result = PowangTypeMap(func.return_type.type)()
                call_final_result.weak = func.return_type.weak
                call_final_result.const = func.return_type.const
                assign_variable_with_checks('function return type', call_final_result, call_return_value)

                pop_stack()
                return call_final_result
            raise powang_throw(powang_error_identifier_not_found(where, call_callee))

        case ParserTokenType.IF_STATEMENT:
            new_scope()
            if_expr = expr_value['expression']
            if_block = expr_value['block']
            if_else_block = expr_value['else']
            
            if new_scope() and PowangBoolean.cast(evaluate_ast_expression(if_expr)).data:
                new_scope()
                for if_statement in if_block['value']:
                    evaluate_ast_expression(if_statement)
                pop_stack()
            elif if_else_block is not None:
                new_scope()
                for if_statement in if_else_block['value']:
                    evaluate_ast_expression(if_statement)
                pop_stack()
            pop_stack()
            return PowangNova()
                    
        case ParserTokenType.FOR_STATEMENT:
            for_start_expression = expr_value['start_expression']
            for_middle_expression = expr_value['middle_expression']
            for_last_expression = expr_value['last_expression']
            for_block = expr_value['block']

            if for_middle_expression is None:
                for_middle_expression = for_start_expression
                for_start_expression = None
                
            if for_start_expression is not None:
                evaluate_ast_expression(for_start_expression)
            while new_scope() and PowangBoolean.cast(evaluate_ast_expression(for_middle_expression)).data:
                new_scope()
                for statement in for_block['value']:
                    evaluate_ast_expression(statement)
                pop_stack()
                if for_last_expression is not None:
                    evaluate_ast_expression(for_last_expression)
                pop_stack()
            return PowangNova()
        
        case ParserTokenType.FOR_EACH_STATEMENT:
            for_each_iterable_expression = expr_value['expression']

            new_scope()
            for_each_iterable = evaluate_ast_expression(for_each_iterable_expression)
            assert for_each_iterable.type == PowangArray.type, powang_error_format("VALUE", where, "Expression is not an iterable value", [
                f"Expression is of type {for_each_iterable.type}"
            ])
            
            for_each_iterator_expression = expr_value['iterator']

            for_each_block = expr_value['block']
            i = 0
            while new_scope() and i < len(for_each_iterable.data):
                iterator = evaluate_ast_expression(for_each_iterator_expression)
                assign_variable_with_checks('for each', iterator, for_each_iterable.data[i])
                if expr_value['if_expression'] is not None:
                    if not evaluate_ast_expression(expr_value['if_expression']).data:
                        pop_stack()
                        i += 1
                        continue
                new_scope()
                for for_each_statement in for_each_block['value']:
                    evaluate_ast_expression(for_each_statement)
                pop_stack()
                pop_stack()
                i += 1
                 
        case ParserTokenType.DECLARATION_FUN:
            fun_return_type: DictRepr = expr_value['return']['value']
            assert fun_return_type['value'] in TYPES, powang_error_identifier_type(where, fun_return_type['value'])
            fun_identifier = evaluate_ast_expression(expr_value['identifier'], True)
            assert isinstance(fun_identifier, str), powang_error_syntax_unexpected_token(where, fun_identifier.type, TokenToString(LexerTokenType.IDENTIFIER))
            assert fun_identifier not in TYPES, powang_error_format("NAME", where, f"Function identifier names a type: {fun_identifier}")
            fun_args = expr_value['args']            
            fun_block = expr_value['block']
            return_type = PowangTypeMap(fun_return_type['value'])()
            return_type.weak._it_is = fun_return_type['weak']
            return_type.const = PowangType_Base.PropertyConst(fun_return_type['const'], True)
            functions_stack[-1][fun_identifier] = PowangFunction(
                fun_args, fun_block['value'], return_type
            )
                    
    return PowangNova()

def interpret_program(program: list[DictRepr]):
    result = PowangNova()
    for statement in program:
        result = evaluate_ast_expression(statement)
    return result