from re import match
from .parser import *
from .error import *

from .builtins.output import *
from .builtins.input import *
from .builtins.info import *

from .builtins.cast import * # HELPER

CallableFormat = tuple[int, int, Callable[(...), PowangAny]]

BUILTINS: dict[str, CallableFormat] = {
    # OUTPUT
    'output': (1, -1, builtin_output),
    'format': (1, -1, builtin_format),
    'printf': (1, -1, builtin_printf),

    # INPUT
    'input' : (0,  1, builtin_input ),

    # INFO
    'size'  : (1, -1, builtin_size  ),
    'typeof': (1,  1, builtin_typeof),
}

class ScopeStack:
    variables: list[dict[str, PowangAny]] = [{}]
    functions: list[dict[str, list[PowangFunction]]] = [{}]

    @staticmethod
    def get_variable(name: str):
        for scope in ScopeStack.variables[::-1]:
            if (value := scope.get(name)) is not None:
                return value
        return None

    @staticmethod
    def get_functions(name: str) -> list[PowangFunction] | None:
        for scope in ScopeStack.functions[::-1]:
            if (func := scope.get(name)) is not None:
                return func
        return None

    @staticmethod
    def new_variable(name: str, value: PowangAny):
        ScopeStack.variables[-1][name] = value
        return value

    @staticmethod
    def new_function(name: str, value: PowangFunction):
        ScopeStack.functions[-1].setdefault(name, []).append(value)
        return value

    @staticmethod
    def pop():
        ScopeStack.variables.pop()
        ScopeStack.functions.pop()
        return True

    @staticmethod
    def push():
        ScopeStack.variables.append({})
        ScopeStack.functions.append({})
        return True

def assignWithChecks(where: str, target_value: PowangAny, right_value: PowangAny):
    if right_value.type == PowangSome.type:
        right_value = PowangTypeMap(right_value.some)(right_value.data)

    if target_value.const:
        assert not target_value.defined or target_value.const.can_change, powang_error_format(
            "CONST", where, "Trying to assign to a strong const", [
                f"{right_value.type} -> {target_value.type}!"
            ])
        target_value.const.can_change = False

    if target_value.type == PowangSome.type:
        target_value.data = PowangTypeMap(right_value.type)(right_value.data).data
        target_value.some = right_value.type
    else:
        target_value.data = checkTypes(where, target_value.type, right_value, target_value.weak._it_is).data # type: ignore
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

def checkTypes(where: str, target_type: str, right_value: PowangAny, target_is_weak: bool) -> PowangAny:
    if not target_is_weak and target_type != PowangNova.type:
        assert right_value.weak.has_value, powang_error_strong_nova_assign(where, target_type)
    elif not right_value.weak.has_value:
        return PowangNova()

    if target_type != PowangSome.type and target_type != right_value.type:
        assert (casted_right_value := PowangCast(target_type, right_value)) is not None, powang_error_type_match(
            where,
            target_type,
            right_value.type
        )
        return PowangCopyConstruct(casted_right_value)
    return PowangCopyConstruct(right_value)

def getIndexedValue(where: str, expression: DictRepr, subscript_check: bool):
    target_value = evaluateAstExpression(expression['target'])
    assert target_value.defined, powang_error_undefined_reference(
        TokenToString(ParserTokenType.ASSIGNMENT),
        expression['target']['value']
    )

    if target_value.type == PowangSome.type:
        target_value = PowangTypeMap(target_value.some)(target_value.data)

    index = evaluateAstExpression(expression['index'])

    if subscript_check:
        assert target_value.type != PowangString.type, powang_error_format("ASSIGN", where, "string type is not subscriptable for now.")
    
    return target_value.index(index)

def getValidIdentifier(where: str, identifier: DictRepr) -> str:
    identifier_name = evaluateAstExpression(identifier, True)
    assert isinstance(identifier_name, str), powang_error_syntax_unexpected_token(
        where, identifier_name.type, TokenToString(LexerTokenType.IDENTIFIER)
    )
    return identifier_name

def getUndefinedVariable(where: str, type_expression: DictRepr):
    assert type_expression['value'] in TYPES, powang_error_identifier_type(where, type_expression['value'])

    undefined_weak = PowangTypeBase.PropertyWeak(type_expression['weak'], False)
    undefined_const = PowangTypeBase.PropertyConst(type_expression['const'], True)
    undefined_right_value = PowangTypeMap(type_expression['value'])()
    undefined_right_value.weak   = undefined_weak
    undefined_right_value.const  = undefined_const
    undefined_right_value.defined = False
    return undefined_right_value

def evaluateAstExpression(expression: DictRepr, is_identifier: bool = False) -> PowangAny:
    if expression == {}:
        return PowangNova()

    # from icecream import ic

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
                        return explicitCastinteger(PowangString(explicitCaststring(unary_right).data[::-1])) # type: ignore
                    if unary_right.type == PowangNumber.type:
                        return explicitCastnumber(PowangString(explicitCaststring(unary_right).data[::-1])) # type: ignore
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
            binary_left = evaluateAstExpression(expr_value['left'])
            if binary_left.type == PowangSome.type:
                binary_left = PowangTypeMap(binary_left.some)(binary_left.data)
            binary_operator = expr_value['operator']['value']
            binary_right = expr_value['right']['value']
            if binary_operator == 'as':
                assert binary_right in TYPES, powang_error_identifier_type(where, binary_right)

                # EXPLICIT CASTING
                assert (binary_casted := explicitCast(binary_right, binary_left)) is not None, powang_error_invalid_cast(
                    None,
                    binary_right,
                    binary_left.type,
                    True,
                )
                binary_value = PowangCopyConstruct(binary_casted)
                return binary_value
            elif binary_operator in {'::', '!:'}:
                if binary_right not in TYPES:
                    binary_right = evaluateAstExpression(expr_value['right']).type
                match binary_operator:
                    case '::':
                        return PowangBoolean(binary_left.type == binary_right)
                    case '!:':
                        return PowangBoolean(binary_left.type != binary_right)
            elif binary_operator == '&&':
                if not PowangBoolean.cast(binary_left).data:
                    return PowangBoolean(False)
                return PowangBoolean.cast(evaluateAstExpression(expr_value['right']))
            elif binary_operator == '||':
                if PowangBoolean.cast(binary_left).data:
                    return PowangBoolean(True)
                return PowangBoolean.cast(evaluateAstExpression(expr_value['right']))

            binary_right = evaluateAstExpression(expr_value['right'])
            binary_operator = expr_value['operator']['value']
            return perform_operation(binary_operator, binary_left, binary_right, expr_value['typed'])

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
            typed_variable = assignWithChecks(where, undefined_value, right_value)
            ScopeStack.new_variable(expr_value['identifier']['value'], typed_variable)
            return typed_variable

        case ParserTokenType.DECLARATION_INTERPRET:
            typed_identifier = getValidIdentifier(where, expr_value['identifier'])
            assert typed_identifier not in ScopeStack.variables[-1], powang_error_format('REDEFINE', where, "Cannot redefine variables", [
                f"redefined: {typed_identifier}"
            ])
            right_value = evaluateAstExpression(expr_value['expression'])
            interpret_variable = getUndefinedVariable(where, {
                "value" : {PowangSome.type: right_value.some}.get(right_value.type, right_value.type),
                "weak" : right_value.weak._it_is,
                "const": right_value.const._it_is,
            })
            assignWithChecks(where, interpret_variable, right_value)
            ScopeStack.new_variable(expr_value['identifier']['value'], interpret_variable)
            return interpret_variable

        case ParserTokenType.ASSIGNMENT:
            assign_target = expr_value['target']

            if assign_target['type'] == ParserTokenType.INDEX_EXPRESSION:
                assign_target_value = getIndexedValue(where, assign_target, True)
            else:
                assign_target = getValidIdentifier(where, assign_target)
                assert (assign_target_value := ScopeStack.get_variable(assign_target)) is not None, powang_error_identifier_not_found(
                    where,
                    assign_target,
                )

            assign_value = evaluateAstExpression(expr_value['expression'])
            assignWithChecks(where, assign_target_value, assign_value)
            return assign_value

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
                candidate: PowangFunction | None = match_functions[0]
                for match_func in match_functions[1:]:
                    match_arguments = True
                    for match_arg, param in zip(match_func.args, call_parameters):
                        if not match_arg['value']['type']['value']['weak'] and not param.weak.has_value:
                            match_arguments = False
                            break
                        if match_arg['value']['type']['value']['value'] != param.type:
                            match_arguments = False
                            break
                        
                    if match_arguments:
                        candidate = match_func
                        break
                    
                assert candidate is not None, powang_error_format('TYPE', where, "There's no function that matches the parameter list", [
                    ', '.join([param.type for param in call_parameters])
                ])
                    
                min_argc: int = 0
                ScopeStack.push()
                for i, call_arg in enumerate(candidate.args):
                    call_argument = evaluateAstExpression(call_arg)
                    if call_arg['type'] == ParserTokenType.DECLARATION_UNDEFINED:
                        min_argc += 1
                    
                    if i < len(call_parameters):
                        assignWithChecks('function call', call_argument, call_parameters[i])

                assert len(call_parameters) <= len(candidate.args), powang_error_format("ARGUMENT", 'Function call', 'too many arguments')
                assert len(call_parameters) >= min_argc, powang_error_format("ARGUMENT", 'Function call', 'not enought arguments')

                for i, call_arg in enumerate(call_parameters):
                    assert call_arg.defined, powang_error_undefined_argument(call_callee, i + 1, call_arg.type)
                
                return_value: PowangAny = PowangNova()
                ScopeStack.push()
                for call_statement in candidate.data:
                    return_value = evaluateAstExpression(call_statement)
                ScopeStack.pop()

                call_final_result = PowangCopyConstruct(candidate.return_type)
                assignWithChecks('function return type', call_final_result, return_value)

                ScopeStack.pop()
                return call_final_result
            raise powang_throw(powang_error_identifier_not_found(where, call_callee))

        case ParserTokenType.IF_STATEMENT:
            ScopeStack.push()
            if_expr = expr_value['expression']
            if_block = expr_value['block']
            if_else_block = expr_value['else']

            if ScopeStack.push() and PowangBoolean.cast(evaluateAstExpression(if_expr)).data:
                ScopeStack.push()
                for if_statement in if_block['value']:
                    evaluateAstExpression(if_statement)
                ScopeStack.pop()
            elif if_else_block is not None:
                ScopeStack.push()
                for if_statement in if_else_block['value']:
                    evaluateAstExpression(if_statement)
                ScopeStack.pop()
            ScopeStack.pop()
            ScopeStack.pop()
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
                evaluateAstExpression(for_start_expression)
            while ScopeStack.push() and PowangBoolean.cast(evaluateAstExpression(for_middle_expression)).data:
                ScopeStack.push()
                for statement in for_block['value']:
                    evaluateAstExpression(statement)
                ScopeStack.pop()
                if for_last_expression is not None:
                    evaluateAstExpression(for_last_expression)
                ScopeStack.pop()
            return PowangNova()

        case ParserTokenType.FOR_EACH_STATEMENT:
            for_each_iterable_expression = expr_value['expression']

            ScopeStack.push()
            for_each_iterable = evaluateAstExpression(for_each_iterable_expression)
            assert for_each_iterable.type == PowangArray.type, powang_error_format("VALUE", where, "Expression is not an iterable value", [
                f"Expression is of type {for_each_iterable.type}"
            ])

            for_each_iterator_expression = expr_value['iterator']

            for_each_block = expr_value['block']
            for current_item in for_each_iterable.iterate().data:
                ScopeStack.push()
                iterator = evaluateAstExpression(for_each_iterator_expression)
                assignWithChecks('for each', iterator, current_item)
                if expr_value['if_expression'] is not None:
                    if not evaluateAstExpression(expr_value['if_expression']).data:
                        ScopeStack.pop()
                        continue
                ScopeStack.push()
                for for_each_statement in for_each_block['value']:
                    evaluateAstExpression(for_each_statement)
                ScopeStack.pop()
                ScopeStack.pop()
            ScopeStack.pop()

        case ParserTokenType.DECLARATION_FUN:
            return_type = getUndefinedVariable(where, expr_value['return']['value'])
            fun_identifier = getValidIdentifier(where, expr_value['identifier'])
            fun_args = expr_value['args']
            assert fun_identifier not in TYPES, powang_error_identifier_names_type(where, fun_identifier)
            functions: list[PowangFunction] | None = ScopeStack.get_functions(fun_identifier)
            if functions is not None:
                for func in functions:
                    if len(func.args) == len(fun_args):
                        for found_arg, new_arg in zip(func.args, fun_args):
                            assert found_arg['value']['type'] != new_arg['value']['type'], powang_error_redefined(where, fun_identifier, [
                                f"remember, return types doesn't determine function signatures"
                            ])
            ScopeStack.new_function(fun_identifier, PowangFunction(
                fun_args,
                expr_value['block']['value'],
                return_type
            ))

    return PowangNova()

def interpret_program(program: list[DictRepr]):
    result = PowangNova()
    for statement in program:
        result = evaluateAstExpression(statement)
    return result