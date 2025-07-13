
from .parser import *
from .error import *
from .builtins import *
from .scopestack import ScopeType, ScopeStack
from .lexer import *

from icecream import ic as log

def getValidIdentifier(where: str, identifier: DictRepr) -> str:
    identifier_name = evaluateAstExpression(identifier, True)
    assert isinstance(identifier_name, str), powang_error_syntax_unexpected_token(
        where, identifier_name.type, TokenToString(LexerTokenType.IDENTIFIER))
    return identifier_name

def getUndefinedVariable(where: str, type_expression: DictRepr):
    if type_expression['value'] in TYPE_ALIAS:
        type_expression = TYPE_ALIAS[type_expression['value']]
    if type_expression['value'] in NATI_TYPES:
        undefined_right_value = PowangTypeMap(type_expression['value'])()
    else:
        assert (user_type := ScopeStack.get_ObjectType(type_expression['value'])) is not None, powang_error_identifier_type(
            where, type_expression['value']
        )
        undefined_right_value = PowangCopyConstruct(user_type)
    undefined_right_value.defined = False
    undefined_weak = PowangTypeBase.PropertyWeak(type_expression['weak'], False)
    undefined_const = PowangTypeBase.PropertyConst(type_expression['const'], True)
    undefined_right_value.weak   = undefined_weak
    undefined_right_value.const  = undefined_const
    return undefined_right_value

def checkObjectTypes(where: str, target_value: PowangObjectType, right_value: PowangAny) -> PowangObjectType:
    if checkReturnsNova(where, target_value, right_value):
        return target_value

    user_type = ScopeStack.get_existingObjectType(target_value.type_name)

    if right_value.type != PowangArray.type:
        right_value = PowangArray([right_value])

    casted_value = castToObjectType(where, user_type, target_value, right_value)
    return casted_value

def castToObjectType(where: str, user_type: PowangObjectType, target_value: PowangObjectType, right_value: PowangArray) -> PowangObjectType:
    constructor_methods = user_type.getConstructors()
    constructor_return: Optional[PowangAny] = None
    constructor_candidate = getFunctionCandidate(constructor_methods, right_value.data)
    constructor_return = callMethod(where, user_type, CONSTRUCTOR_METHOD_NAME, constructor_candidate, right_value.data)
    assert constructor_return.type == PowangObjectType.type and constructor_return.type_name == user_type.type_name, powang_error_type_match(where, target_value.type_name, constructor_return.type_name)
    return constructor_return


def checkReturnsNova(where: str, target_value: PowangAny, right_value: PowangAny) -> bool:
    if not target_value.weak.it_is and target_value.type != PowangNova.type:
        assert right_value.weak.has_value, powang_error_strong_nova_assign(where, target_value.type)

    elif not right_value.weak.has_value:
        return True
    return False

def checkTypes(where: str, target_value: PowangAny, right_value: PowangAny) -> PowangAny:
    if checkReturnsNova(where, target_value, right_value):
        return target_value

    if target_value.type != right_value.type and target_value.type != PowangSome.type:
        assert (casted_right_value := PowangTypeCast(target_value.type, right_value)) is not None, powang_error_type_match(
            where,
            target_value.type,
            right_value.type)
        return PowangCopyConstruct(casted_right_value)
    return PowangCopyConstruct(right_value)

def assignWithChecks(where: str, target_value: PowangAny, right_value: PowangAny, force_object_assign: bool):
    if right_value.type == PowangSome.type:
        right_value = PowangTypeMap(right_value.some)(right_value.data)
    
    if target_value.const:
        assert not target_value.defined or target_value.const.can_change, powang_error_format(
            "CONST", where, "Trying to assign to a strong const", [
                f"{right_value.type} -> {target_value.type}!"])
        target_value.const.can_change = False


    if target_value.type == PowangSome.type:
        target_value.data = PowangTypeMap(right_value.type)(right_value.data).data
        target_value.some = right_value.type

    elif target_value.type == PowangObjectType.type:
        copy_constructor_result: Optional[PowangAny] = None
        if areSameObjectType(target_value, right_value) and right_value.type == PowangObjectType.type:
            if not force_object_assign:
                target_value.defined = True
                target_value.weak.has_value = right_value.weak.has_value
                for const in target_value.getConstructors():
                    if len(const.args) == 1 and const.args[0]['value']['type']['value']['value'] == target_value.type_name:
                        copy_constructor_result = callMethod(where, target_value, CONSTRUCTOR_METHOD_NAME, const, [right_value])
                        break
            check_result = copy_constructor_result \
            if copy_constructor_result is not None and copy_constructor_result.type == PowangObjectType.type \
            else right_value
        else:
            check_result = checkObjectTypes(where, target_value, right_value)
        target_value.data = check_result.data
        target_value.private_props = check_result.private_props
    else:
        check_result = checkTypes(where, target_value, right_value)
        target_value.data = check_result.data # type: ignore

    target_value.defined = True
    target_value.weak.has_value = right_value.weak.has_value
    return target_value

def performOperation(operator: str, left: PowangAny, right: PowangAny, typed: bool) -> PowangAny:
    if left.type == PowangSome.type:
        left = PowangTypeMap(left.some)(left.data)
    if right.type == PowangSome.type:
        right = PowangTypeMap(right.some)(right.data)
    if operator in {'+', '-', '*', '/'}:
        assert left.type != PowangNova.type and left.weak.has_value, powang_error_unsupported_operation(
            'operation', f'nova weak {left.type}', operator, right.type)
        assert right.type != PowangNova.type and right.weak.has_value, powang_error_unsupported_operation(
            'operation', left.type, operator, f'nova weak {right.type}')
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
                casted = PowangTypeCast(left.type, right)
                assert casted is not None, powang_error_unsupported_operation('comparisson', left.type, operator, right.type)
                return performOperation(operator, left, casted, False)
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
            casted = PowangTypeCast(right.type, left)
            assert casted is not None, powang_error_unsupported_operation('implicit typed operation', left.type, operator, right.type)
            return performOperation(operator, casted, right, False)
        else:
            casted = PowangTypeCast(left.type, right)
            assert casted is not None, powang_error_unsupported_operation('implicit operation', left.type, operator, right.type)
        return performOperation(operator, left, casted, typed)
    return result

def getIndexedValue(where: str, expression: DictRepr, subscript_check: bool):
    target_value = evaluateAstExpression(expression['target'])
    assert target_value.defined, powang_error_undefined_reference(
        TokenToString(ParserTokenType.ASSIGNMENT),
        expression['target']['value'])
    if target_value.type == PowangSome.type:
        target_value = PowangTypeMap(target_value.some)(target_value.data)
    index = evaluateAstExpression(expression['index'])
    if subscript_check:
        assert target_value.type != PowangString.type, powang_error_format("ASSIGN", where, "string type is not subscriptable for now.")
    return target_value.index(index)

def getFunctionCandidate(match_functions: list[PowangFunction], call_parameters: list[PowangAny]):
    candidates: list[int] = [0] * len(match_functions)
    max_index: int = 0
    for func_index, match_func in enumerate(match_functions):
        if len(call_parameters) == len(match_func.args):
            candidates[func_index] += 3
        elif len(call_parameters) == match_func.min_argc:
            candidates[func_index] += 2
        for match_arg, param in zip(match_func.args, call_parameters):
            match_arg_type = match_arg['value']['type']['value']['value']
            if match_arg_type == param.type_name:
                candidates[func_index] += 3
            elif match_arg_type == param.type:
                candidates[func_index] += 3
            elif match_arg_type == PowangSome.type:
                candidates[func_index] += 2
            elif match_arg_type in NATI_TYPES:
                if PowangTypeCast(match_arg_type, param) is not None:
                    candidates[func_index] += 1
                else:
                    candidates[func_index] -= 1
            else:
                candidates[func_index] += 1
            if match_arg['value']['type']['value']['weak']:
                if param.weak:
                    candidates[func_index] += 1
                if not param.weak.has_value:
                    candidates[func_index] += 2
            elif not param.weak.it_is:
                candidates[func_index] += 1
        if max(candidates) == candidates[func_index]:
            max_index = func_index
    return match_functions[max_index]

def areSameObjectType(left: PowangAny, right: PowangAny):
    return (
        left.type == PowangObjectType.type and \
        left.type_name == right.type_name
    )

def callFunction(where: str, callee: str, candidate: PowangFunction, call_parameters: list[PowangAny]):
    ScopeStack.push(ScopeType.FUNCTION)
    for i, call_arg in enumerate(candidate.args):
        call_argument = evaluateAstExpression(call_arg)

        if i < len(call_parameters):
            assignWithChecks('function call', call_argument, call_parameters[i],
               areSameObjectType(call_argument, call_parameters[i])
                # force object assign condition
            )

    assert len(call_parameters) <= len(candidate.args), powang_error_format("ARGUMENT", 'Function call', 'too many arguments')
    assert len(call_parameters) >= candidate.min_argc, powang_error_format("ARGUMENT", 'Function call', 'not enought arguments')

    for i, call_arg in enumerate(call_parameters):
        assert call_arg.defined, powang_error_undefined_argument(callee, i + 1, call_arg.type)

    return_value: PowangAny = PowangNova()
    ScopeStack.push(ScopeType.FUNCTION)
    for call_statement in candidate.data:
        evaluateAstExpression(call_statement)
        if ScopeStack.return_value is not None:
            return_value = PowangCopyConstruct(ScopeStack.return_value)
            ScopeStack.return_value = None
            break
    ScopeStack.pop()
    
    return_expression_value = getUndefinedVariable(where, candidate.return_expr)
    assignWithChecks(f'function return: {callee}', return_expression_value, return_value,
        areSameObjectType(return_expression_value, return_value)
    )
    
    ScopeStack.pop()
    return return_expression_value

def callMethod(where: str, owner: PowangObjectType, method_name: str, method: PowangFunction, arguments: list[PowangAny]):
    ScopeStack.method_call_stack.append(owner)
    return_value = callFunction(where, method_name, method, arguments)
    ScopeStack.method_call_stack.pop()
    return return_value

def getValidType(type: str) -> Optional[str]:
    if type in TYPE_ALIAS:
        type = TYPE_ALIAS[type]['value']
    if type in NATI_TYPES:
        return type
    return None

def evaluateAstExpression(expression: DictRepr, is_identifier: bool = False) -> PowangAny:
    if expression == {}:
        return PowangNova()

    where = TokenToString(expression['type'])
    expr_value = expression['value']
    match expression['type']:
        case LexerTokenType.IDENTIFIER:
            if expr_value == 'nova':
                return PowangNova()
            if expr_value in {'true', 'false'}:
                return PowangBoolean(expr_value == 'true')
            if expr_value == str('this'):
                if len(ScopeStack.method_call_stack) > 0:
                    this = ScopeStack.method_call_stack[-1]
                    return this
            if is_identifier:
                return expr_value
            assert (identifier_value := ScopeStack.get_variable(expr_value)) is not None, \
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
            unary_right = evaluateAstExpression(expr_value['right'])

            match unary_operator:
                case '!':
                    return PowangBoolean(not PowangBoolean.cast(unary_right).data)
                case '[-]':
                    if unary_right.type == PowangInteger.type:
                        return explicitCastinteger(PowangString(explicitCastString(unary_right).data[::-1])) # type: ignore
                    if unary_right.type == PowangNumber.type:
                        return explicitCastNumber(PowangString(explicitCastString(unary_right).data[::-1])) # type: ignore
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

        case ParserTokenType.BINARY_EXPRESSION:
            binary_operator = expr_value['operator']['value']
            binary_left = evaluateAstExpression(expr_value['left'])
            if binary_operator in {'::', '!:'}:
                type_condition: bool = True
                if expr_value['right']['type'] == LexerTokenType.IDENTIFIER:
                    type_condition = expr_value['right']['value'] == binary_left.type_name

                    # if expr_value['right']['value']['weak']:
                    #     type_condition = type_condition and binary_left.weak.it_is
                    # if expr_value['right']['value']['const']:
                    #     type_condition = type_condition and binary_left.const.it_is
                else:
                    binary_right = evaluateAstExpression(expr_value['right'])
                    if binary_right.weak:
                        type_condition = type_condition and binary_left.weak.it_is
                    if binary_right.const:
                        type_condition = type_condition and binary_left.const.it_is

                if binary_operator == '::':
                    return PowangBoolean(type_condition)
                return PowangBoolean(not type_condition)
                
            binary_right = expr_value['right']['value']
            if binary_operator == 'as':
                if binary_left.type == PowangSome.type:
                    binary_left = PowangTypeMap(binary_left.some)(binary_left.data)
                    
                if binary_right in TYPE_ALIAS:
                    binary_right = TYPE_ALIAS[binary_right]['value']
                if binary_right not in NATI_TYPES:
                    assert (user_type := ScopeStack.get_ObjectType(binary_right)) is not None, powang_error_identifier_type(where, binary_right)
                    check_result = checkObjectTypes(where, user_type, binary_left)
                    return check_result

                # EXPLICIT CASTING
                assert (binary_casted := explicitCast(binary_right, binary_left)) is not None, powang_error_invalid_cast(
                    None,
                    binary_right,
                    binary_left.type,
                    True,
                )
                binary_value = PowangCopyConstruct(binary_casted)
                return binary_value
 
            binary_right = evaluateAstExpression(expr_value['right'])
            if binary_operator in {'&&', '||'}:
                if binary_operator == '&&':
                    if not PowangBoolean.cast(binary_left).data:
                        return PowangBoolean(False)
                    return PowangBoolean.cast(binary_right)
                if PowangBoolean.cast(binary_left).data:
                    return PowangBoolean(True)
                return PowangBoolean.cast(binary_right)

            return performOperation(binary_operator, binary_left, binary_right, expr_value['typed'])

        case ParserTokenType.DECLARATION_UNDEFINED:
            undefined_identifier = getValidIdentifier(where, expr_value['identifier'])
            assert undefined_identifier not in ScopeStack.variables[-1], powang_error_format('REDEFINE', where, "Cannot redefine variables", [
                f"redefined: {undefined_identifier}"
            ])
            undefined_variable = getUndefinedVariable(where, expr_value['type']['value'])
            ScopeStack.new_variable(expr_value['identifier']['value'], undefined_variable)
            return undefined_variable

        case ParserTokenType.DECLARATION_TYPED_VAR:
            typed_identifier = getValidIdentifier(where, expr_value['identifier'])
            assert typed_identifier not in ScopeStack.variables[-1], powang_error_format('REDEFINE', where, "Cannot redefine variables", [
                f"redefined: {typed_identifier}"
            ])
            undefined_value = getUndefinedVariable(where, expr_value['type']['value'])
            right_value = evaluateAstExpression(expr_value['expression'])
            typed_variable = assignWithChecks(where, undefined_value, right_value, False)
            ScopeStack.new_variable(expr_value['identifier']['value'], typed_variable)
            return typed_variable

        case ParserTokenType.DECLARATION_INTERPRET:
            typed_identifier = getValidIdentifier(where, expr_value['identifier'])
            assert typed_identifier not in ScopeStack.variables[-1], powang_error_format('REDEFINE', where, "Cannot redefine variables", [
                f"redefined: {typed_identifier}"
            ])
            right_value = evaluateAstExpression(expr_value['expression'])
            interpret_variable = getUndefinedVariable(where, {
                "weak" : right_value.weak.it_is,
                "const": right_value.const.it_is,
                "value" : {
                    PowangSome.type: right_value.some,
                    PowangObjectType.type: right_value.type_name
                }.get(right_value.type, right_value.type),
            })

            assignWithChecks(where, interpret_variable, right_value, False)
            ScopeStack.new_variable(expr_value['identifier']['value'], interpret_variable)
            return interpret_variable

        case ParserTokenType.ASSIGNMENT:
            assign_target = expr_value['target']

            if assign_target['type'] == ParserTokenType.ACCESS_EXPRESSION:
                assign_target_value = evaluateAstExpression(assign_target)
            elif assign_target['type'] == ParserTokenType.INDEX_EXPRESSION:
                assign_target_value = getIndexedValue(where, assign_target['value'], True)
            else:
                assign_target = getValidIdentifier(where, assign_target)
                assert (assign_target_value := ScopeStack.get_variable(assign_target)) is not None, powang_error_identifier_not_found(
                    where,
                    assign_target,
                )

            assign_value = evaluateAstExpression(expr_value['expression'])
            return assignWithChecks(where, assign_target_value, assign_value, False)

        case ParserTokenType.ARRAY_EXPRESSION:
            array_expr_elements = expr_value['elements']
            if expr_value['type'] == PowangMap.type:
                return PowangMap({
                    evaluateAstExpression(key_value['value']['key']):
                    evaluateAstExpression(key_value['value']['value'])
                    for key_value in array_expr_elements
                })
            array_elements: list = [evaluateAstExpression(array_item) for array_item in array_expr_elements]
            return PowangArray(array_elements)

        case ParserTokenType.INDEX_EXPRESSION:
            index_expression_value = getIndexedValue(where, expression['value'], False)
            assert index_expression_value is not None, powang_error_format(
                'IMPLEMENTATION', where, "Index to that type is not implemented yet."
            )
            return index_expression_value

        case ParserTokenType.CALL_EXPRESSION:
            call_callee = getValidIdentifier(where, expr_value['callee'])
            call_parameters = [evaluateAstExpression(call_arg) for call_arg in expr_value['arguments']]

            if call_callee in BUILTINS:
                call_min_argc, call_max_argc, call_func = BUILTINS[call_callee]
                if call_max_argc != -1:
                    assert len(call_parameters) <= call_max_argc, powang_error_format("ARGUMENT", 'Function call', 'too many arguments')
                assert len(call_parameters) >= call_min_argc, powang_error_format("ARGUMENT", 'Function call', 'not enought arguments')
                return call_func(*call_parameters)

            elif (match_functions := ScopeStack.get_functions(call_callee)) is not None:
                candidate = getFunctionCandidate(match_functions, call_parameters)
                return callFunction(where, call_callee, candidate, call_parameters)
            raise powang_throw(powang_error_identifier_not_found(where, call_callee))

        case ParserTokenType.IF_STATEMENT:
            ScopeStack.push()
            if_expr = expr_value['expression']
            if_block = expr_value['block']
            if_else_block = expr_value['else']

            if ScopeStack.push() and not PowangBoolean.cast(evaluateAstExpression(if_expr)).data:
                if if_else_block is not None:
                      if_block['value'] = if_else_block['value']
                else: if_block = None
                    
            if if_block is not None:
                ScopeStack.push()
                for if_statement in if_block['value']:
                    evaluateAstExpression(if_statement)
                    if ScopeStack.return_value is not None:
                        break
                ScopeStack.pop()
            ScopeStack.pop()

        case ParserTokenType.FOR_STATEMENT:
            for_start_expression = expr_value['start_expression']
            for_middle_expression = expr_value['middle_expression']
            for_last_expression = expr_value['last_expression']
            for_block = expr_value['block']

            if for_middle_expression is None:
                for_middle_expression = for_start_expression
                for_start_expression = None

            if for_start_expression is not None:
                evaluateAstExpression(for_start_expression)

            running: bool = True
            while ScopeStack.push() and PowangBoolean.cast(evaluateAstExpression(for_middle_expression)).data:
                if not running:
                    ScopeStack.pop()
                    break

                ScopeStack.push()
                for statement in for_block['value']:
                    evaluateAstExpression(statement)
                    if ScopeStack.return_value is not None:
                        running = False
                        break
                ScopeStack.pop()
                if running:
                    if for_last_expression is not None:
                        evaluateAstExpression(for_last_expression)
                ScopeStack.pop()

        case ParserTokenType.FOR_EACH_STATEMENT:
            for_each_iterable_expression = expr_value['expression']

            ScopeStack.push()
            for_each_iterable = evaluateAstExpression(for_each_iterable_expression)
            assert for_each_iterable.type == PowangArray.type, powang_error_format("VALUE", where, "Expression is not an iterable value", [
                f"Expression is of type {for_each_iterable.type}"
            ])

            for_each_iterator_expression = expr_value['iterator']

            for_each_block = expr_value['block']

            running: bool = True
            for current_item in for_each_iterable.iterate().data:
                if not running:
                    break

                ScopeStack.push() # iterator assignment
                iterator = evaluateAstExpression(for_each_iterator_expression)
                assignWithChecks('for each', iterator, current_item, False)
                if expr_value['if_expression'] is not None:
                    if not evaluateAstExpression(expr_value['if_expression']).data:
                        ScopeStack.pop()
                        continue

                ScopeStack.push() # for block statement
                for for_each_statement in for_each_block['value']:
                    evaluateAstExpression(for_each_statement)
                    if ScopeStack.return_value is not None:
                        running = False
                        break

                ScopeStack.pop()
                ScopeStack.pop()
            ScopeStack.pop()

        case ParserTokenType.DECLARATION_FUN:
            fun_identifier = getValidIdentifier(where, expr_value['identifier'])
            assert fun_identifier not in NATI_TYPES, powang_error_identifier_names_type(where, fun_identifier)
            functions: list[PowangFunction] | None = ScopeStack.get_functions(fun_identifier)
            if functions is not None:
                for func in functions:
                    if len(func.args) != len(expr_value['args']):
                        continue

                    is_different: bool = False
                    for found_arg, new_arg in zip(func.args, expr_value['args']):
                        if found_arg['value']['type']['value']['value'] != new_arg['value']['type']['value']['value']:
                            is_different = True
                            break

                        if found_arg['value']['type']['value']['weak'] != new_arg['value']['type']['value']['weak']:
                            is_different = True
                            break

                    assert is_different, powang_error_redefined(where, fun_identifier, [
                        f"remember, type qualifiers such as const does not determine function signatures, same with return types"
                    ])

            if expr_value['return'] is None:
                expr_value['return'] = doToken(ParserTokenType.TYPE, {
                    'value': PowangNova.type,
                    'const': False,
                    'weak': False,
                }).toDict()

            new_function = PowangFunction(
                expr_value['args'],
                expr_value['block']['value'],
                expr_value['return']['value']
            )
            new_function.min_argc = expr_value['min_argc']
            return ScopeStack.new_function(fun_identifier, new_function)

        case ParserTokenType.RETURN_EXPRESSION:
            assert ScopeStack.important[-1] == ScopeType.FUNCTION, powang_error_format('LOGIC', None, "Trying to return with a non function scope", [
                f"the scope you are trying to return from it's {ScopeType.toStr(ScopeStack.important[-1])}"
            ])

            ScopeStack.important.pop()
            return_expr_value = evaluateAstExpression(expr_value)
            if return_expr_value.type == PowangSome.type:
                return_expr_value = PowangTypeMap(return_expr_value.some)(return_expr_value.data)
            ScopeStack.return_value = PowangCopyConstruct(return_expr_value)

        case ParserTokenType.TYPE_DECLARATION:
            identifier = getValidIdentifier(where, expr_value['identifier'])
            USER_TYPES.add(identifier)
            ScopeStack.push()
            public_props: dict[str, PowangAny] = {}
            private_props: dict[str, PowangAny] = {}
            for public, prop in expr_value['properties']:
                prop_identifier: str = prop['value']['identifier']['value']
                evaluateAstExpression(prop)
                if public:
                    public_props[prop_identifier] = ScopeStack.variables[-1][prop_identifier]
                else:
                    private_props[prop_identifier] = ScopeStack.variables[-1][prop_identifier]

            public_meths: dict[str, list[PowangFunction]] = {}
            private_meths: dict[str, list[PowangFunction]] = {}
            for public, method in expr_value['methods']:
                method_identifier: str = method['value']['identifier']['value']
                evaluateAstExpression(method)
                if public:
                    public_meths.setdefault(method_identifier, []).append(ScopeStack.functions[-1][method_identifier][-1])
                else:
                    private_meths.setdefault(method_identifier, []).append(ScopeStack.functions[-1][method_identifier][-1])
            ScopeStack.pop()
            USER_TYPES.remove(identifier)
            new_user_type = PowangObjectType(
                public_props, private_props,
                public_meths, private_meths,
            )
            new_user_type.type_name = identifier
            return ScopeStack.new_ObjectType(identifier, new_user_type)

        case ParserTokenType.ACCESS_EXPRESSION:
            target = evaluateAstExpression(expr_value['target'])
            assert target.type == PowangObjectType.type, powang_error_syntax(where, "Invalid access", [
                f"{target.type} cannot be accessed in any way or has no properties"
            ])
            property_identifier = getValidIdentifier(where, expr_value['property'])
            assert target.defined, powang_error_undefined_reference(where, expr_value['target']['value'])
            assert target.weak.has_value, powang_error_format("VALUE", where, f"Invalid access", [
                f"Trying to access property {property_identifier} from a nova weak {target.type_name}"
            ])

            is_private: bool = len(ScopeStack.method_call_stack) > 0
            property_value = target.getProperty(property_identifier, is_private)
            assert property_value is not None, powang_error_identifier_not_found(where, property_identifier, [
                "perhaps it is a private property?"
            ] if not is_private else [])
            return property_value

        case ParserTokenType.METHOD_CALL:
            owner_value = evaluateAstExpression(expr_value['owner'])
            assert owner_value.type == PowangObjectType.type, powang_error_format('IMPLEMENTATION', where,
                "Currently only user types can perform a method call.", [
                    f"but trying to call from a {owner_value.type}"
            ])


            assert (match_methods := owner_value.getMethods(expr_value['method']['value'], len(ScopeStack.method_call_stack) > 0)) is not None, powang_error_identifier_not_found(
                where, f"method: {expr_value['method']['value']}", [
                    "perhaps is a private method?"
                ])

            call_parameters = [evaluateAstExpression(call_arg) for call_arg in expr_value['arguments']]
            method_candidate = getFunctionCandidate(match_methods, call_parameters)
            return callMethod(
                where,
                owner_value,
                expr_value['method']['value'],
                method_candidate,
                call_parameters,
            )

        case ParserTokenType.USE_EXPRESSION:
            for i, use in enumerate(expr_value):
                interpret_program(use, None)
    return PowangNova()

def get_file_content(path: str) -> str:
    with open(path, 'r', encoding='utf-8') as file:
        content = file.read()
        if not content.endswith('\n'):
            content = content + '\n'
        return content

import json

def interpret_program(content: str, ast_output: str | None):
    program_parser = Parser(content)
    try:
        program_raw_ast = program_parser.parse()
        result = PowangNova()
        if ast_output:
            def make_json_serializable(raw_ast):
                if isinstance(raw_ast, dict):
                    return {
                        key: make_json_serializable(value)
                        for key, value in raw_ast.items()
                    }
                elif isinstance(raw_ast, (LexerTokenType, ParserTokenType)):
                    return TokenToString(raw_ast).upper()
                elif isinstance(raw_ast, (list, tuple)):
                    return [make_json_serializable(item) for item in raw_ast]
                else:
                    return raw_ast
                    
            ast_dict = make_json_serializable(program_raw_ast)

            with open(ast_output, 'w', encoding='utf-8') as json_ast:
                json_ast.write(json.dumps(ast_dict, indent=4, ensure_ascii=False))
        for statement in program_raw_ast:
            result = evaluateAstExpression(statement)
        return result
    except AssertionError as ass:
        powang_throw(f"ln: {program_parser.tokenizer.row + 1} | " + ass.args[0])