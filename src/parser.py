from .lexer import *
from .powang_types import *

NATI_TYPES: set[str] = {
    PowangNova.type   ,
    PowangSome.type   ,
    PowangInteger.type,
    PowangNumber.type ,
    PowangBoolean.type,
    PowangString.type ,
    PowangArray.type  ,
    PowangMap.type    ,
}

USER_TYPES = set[str]()
TYPE_ALIAS: dict[str, DictRepr] = {}

from pathlib import Path

PATHS = dict[str, Path]()

class Parser:
    def __init__(self, data: str):
        self.data = data
        self.tokenizer = Tokenizer(data)
        self.next = self.tokenizer.getNextToken()

    def parse(self):
        return self.Program()

    def Program(self):
        body: list[DictRepr] = []
        while self.next.type != LexerTokenType.END_OF_FILE:
            stmt = self.ExpressionStatement()
            if stmt is not None:
                body.append(stmt)
        return body

    def ExpressionStatement(self):
        if self.next.type == LexerTokenType.END_OF_FILE:
            return None
        if self.next.type == LexerTokenType.KEYWORD:
            keyword = self.next.value
            self.consume(LexerTokenType.KEYWORD)
            match keyword:
                case 'if':
                    return self.helper_IfStatement()
                case 'for':
                    return self.helper_ForStatement()
                case 'fun':
                    return self.helper_FunDeclaration()
                case 'return':
                    return doToken(ParserTokenType.RETURN_EXPRESSION, self.Expression()).toDict()
                case 'type':
                    identifier = self.Identifier()
                    if self.next.type == LexerTokenType.RIGHT_ARROW:
                        self.advance()
                        type = self.Type()
                        TYPE_ALIAS[identifier['value']] = type['value']
                        return None
                    return self.helper_TypeObjectDeclaration(identifier)
                case 'use':
                    return self.helper_UseModule()
                case 'extern':
                    return self.helper_ExternSignature()
                case _:
                    raise NotImplementedError(f"{keyword} not implemented yet.")
        else:
            expression = self.Statement()
            self.consume(LexerTokenType.SEMI_COLON)
            return expression

    def helper_ExternSignature(self):
        if self.isNextKeyword('fun'):
            self.advance()
            powang_mapping = self.helper_FunDeclaration()
            assert powang_mapping['value']['block']['value'] is None, powang_error_syntax('extern function', "Expected function signature but function definition was encountered")
        else:
            assert self.isNextKeyword('type'), powang_error_syntax('extern signature', "There's only external functions and types", [
                f"encountered: {TokenToString(self.next.type)}"
            ])
            self.advance()
            identifier = self.Identifier()
            powang_mapping = self.helper_TypeObjectDeclaration(identifier, True)
            assert powang_mapping['value']['properties'] is None, powang_error_syntax('extern type', "Expected type signature but type definition was encountered")
            powang_mapping['value']['properties'] = []
            powang_mapping['value']['methods'] = []
        self.consume(LexerTokenType.RIGHT_ARROW, 'extern mapping')
        python_value = self.StringLiteral()
        return doToken(ParserTokenType.EXTERN_REFERENCE, {
            "powang": powang_mapping,
            "python": python_value['value'],
        }).toDict()

    def helper_UseModule(self):
        if self.next.type == LexerTokenType.IDENTIFIER:
                module_path = PATHS['ABSOLUTE'].parent / 'modules' / self.Identifier()['value']
        else: module_path = PATHS['RELATIVE'].parent / Path(self.StringLiteral()['value'])

        self.consume(LexerTokenType.SEMI_COLON)
        modules: list[str] = []

        try:
            if module_path.is_dir():
                for path in module_path.iterdir():
                    with open(path) as file:
                        modules.append(file.read())
            else:
                assert module_path != Path(__name__), powang_error_format("IMPORT", 'module using', "Is importing the same module")
                with open(module_path) as file:
                    modules = [file.read()]
        except FileNotFoundError:
            assert False, powang_error_format("MODULE", 'using', f"Can't find the module: {module_path}")
        return doToken(ParserTokenType.USE_EXPRESSION, modules).toDict()

    def helper_TypeObjectDeclaration(self, identifier: DictRepr, is_signature: bool = False):
        assert identifier['value'] not in NATI_TYPES, powang_error_redefined(
            TokenToString(ParserTokenType.TYPE_DECLARATION),
            identifier['value'], [
                "a powang native type"
            ]
        )
        assert identifier['value'] not in TYPE_ALIAS, powang_error_redefined(
            TokenToString(ParserTokenType.TYPE_DECLARATION),
            identifier['value'], [
                f"a type alias for {TYPE_ALIAS[identifier['value']]['value']}"
            ]
        )
        assert identifier['value'] not in {'true', 'false'}, powang_error_redefined(
            TokenToString(ParserTokenType.TYPE_DECLARATION),
            identifier['value'], [
                f"which is a literal boolean value"
            ]
        )
        
        if is_signature:
            return doToken(ParserTokenType.TYPE_DECLARATION, {
                'identifier' : identifier,
                'properties' : None,
                'methods'    : None,
            }).toDict()  
        
        properties: list[tuple[bool, DictRepr]] = []
        methods   : list[tuple[bool, DictRepr]] = []
        self.consume(LexerTokenType.LEFT_BRACE)
        has_default_constructor: bool = False
        while self.next.type != LexerTokenType.RIGHT_BRACE:
            assert self.next.type in {
                LexerTokenType.OPERATOR_PLUS,
                LexerTokenType.OPERATOR_MINUS
            },  powang_error_syntax_unexpected_token(
                TokenToString(ParserTokenType.TYPE_DECLARATION),
                TokenToString(self.next.type),
                'privacy operator + or -'
            )
            
            is_public: bool = self.next.type == LexerTokenType.OPERATOR_PLUS
            self.advance()
            statement = self.ExpressionStatement()
            assert statement is not None, powang_error_syntax('type declaration', "Reached end of file")
            if statement['type'] in {
                ParserTokenType.DECLARATION_UNDEFINED,
                ParserTokenType.DECLARATION_TYPED_VAR
            }:  properties.append((is_public, statement))
            elif statement['type'] == ParserTokenType.DECLARATION_FUN:
                fun_identifier = statement['value']['identifier']
                fun_return     = statement['value']['return']
                if fun_identifier['value'] == CONSTRUCTOR_METHOD_NAME:
                    assert is_public, powang_error_format('LOGIC', 'constructor declaration', "Type constructor must be public")
                    if len(statement['value']['args']) == 0:
                        has_default_constructor = True
                    # Sets the default constructor return type to the object type
                    if fun_return is None:
                        statement['value']['return'] = self.simulate_Type(identifier['value'], False, False)
                    else:
                        # Check if the return type matches the object type
                        assert fun_return['value']['value'] == identifier['value'], powang_error_format(
                            'LOGIC', 'constructor declaration', 'Return type must be the object type', [
                                f'expected {identifier['value']}',
                                f'but {fun_return['value']['value']} was encountered'
                            ]
                        )
                    
                    # Return "this" default return
                    statement['value']['block']['value'].append(
                        doToken(ParserTokenType.RETURN_EXPRESSION, self.simulate_Identifier('this')
                    ).toDict())
                methods.append((is_public, statement))
        self.advance()

        if not has_default_constructor:
            methods.append((True, doToken(ParserTokenType.DECLARATION_FUN, {
                'identifier': self.simulate_Identifier(CONSTRUCTOR_METHOD_NAME),
                'args': [],
                'min_argc': 0,
                'return': self.simulate_Type(identifier['value'], False, False),
                'block': doToken(ParserTokenType.BLOCK_STATEMENT, [
                    doToken(ParserTokenType.RETURN_EXPRESSION, self.simulate_Identifier('this')).toDict(),
                ]).toDict()
            }).toDict()))

        return doToken(ParserTokenType.TYPE_DECLARATION, {
            'identifier' : identifier,
            'properties' : properties,
            'methods'    : methods,
        }).toDict()

    def Statement(self):
        expr = self.Expression()        

        if self.next.type in {
            LexerTokenType.OPERATOR_ASSIGNMENT_PLUS,
            LexerTokenType.OPERATOR_ASSIGNMENT_MINUS,
            LexerTokenType.OPERATOR_ASSIGNMENT_STAR,
            LexerTokenType.OPERATOR_ASSIGNMENT_SLASH,
        }:
            operator = self.advance()
            value = self.Expression()
            return doToken(ParserTokenType.ASSIGNMENT, {
                "target": expr,
                "expression": doToken(ParserTokenType.BINARY_EXPRESSION, {
                    "left": expr,
                    "operator": LexerToken({
                        LexerTokenType.OPERATOR_ASSIGNMENT_PLUS: LexerTokenType.OPERATOR_PLUS,
                        LexerTokenType.OPERATOR_ASSIGNMENT_MINUS: LexerTokenType.OPERATOR_MINUS,
                        LexerTokenType.OPERATOR_ASSIGNMENT_STAR: LexerTokenType.STAR,
                        LexerTokenType.OPERATOR_ASSIGNMENT_SLASH: LexerTokenType.SLASH,
                    }[operator.type], operator.value[:-1]).toDict(),
                    "right": value,
                    "typed": False,
                }).toDict(),
            }).toDict()

        # Si el próximo token es "=", esto es una asignación
        if self.next.type == LexerTokenType.OPERATOR_ASSIGNMENT:
            self.consume(LexerTokenType.OPERATOR_ASSIGNMENT)
            value = self.Expression()

            return doToken(ParserTokenType.ASSIGNMENT, {
                "target": expr,
                "expression": value,
            }).toDict()
        return expr
    
    def isNextKeyword(self, keyword: str):
        return self.next.type == LexerTokenType.KEYWORD and self.next.value == keyword
    
    def helper_IfStatement(self):
        if self.next.type == LexerTokenType.LEFT_PARENTHESIS:
              expr = self.ParenthesizedExpression()
        else: expr = self.Expression()
            
        if self.next.type == LexerTokenType.LEFT_BRACE:
            block = self.BlockStatement()
        else:
            block = self.ExpressionStatement()
            assert block is not None, powang_error_syntax('if expression', "Reached end of file")
            block = doToken(ParserTokenType.BLOCK_STATEMENT, [block]).toDict()
        
        else_block: DictRepr | None = None

        if self.isNextKeyword('else'):
            self.advance()
            if self.next.type == LexerTokenType.LEFT_BRACE:
                else_block = self.BlockStatement()
            else:
                else_block = self.ExpressionStatement()
                assert else_block is not None, powang_error_syntax('else expression', "Reached end of file")
                else_block = doToken(ParserTokenType.BLOCK_STATEMENT, [else_block]).toDict()

        return doToken(ParserTokenType.IF_STATEMENT, {
            "expression": expr,
            "block": block,
            "else": else_block,
        }).toDict()
        
    def helper_ForStatement(self):
        has_paren = False
        if self.next.type == LexerTokenType.LEFT_PARENTHESIS:
            self.consume(LexerTokenType.LEFT_PARENTHESIS)
            has_paren = True

        start_expression = self.Statement()
        
        if start_expression['type'] == ParserTokenType.DECLARATION_UNDEFINED:
            if_expression: DictRepr | None = None
            if self.next.type == LexerTokenType.RIGHT_ARROW:
                self.advance()
                iterable_expression = self.Expression()
                if self.next.type == LexerTokenType.KEYWORD:
                    assert self.next.value == 'if', powang_error_syntax('for each expression', f"{self.next.value} is not a valid keyword in this context", [
                        "for each last expression only accepts if keyword"
                    ])
                    self.advance()
                    if_expression = self.Expression()
                block = self.BlockStatement()
                return doToken(ParserTokenType.FOR_EACH_STATEMENT, {
                    "iterator": start_expression,
                    "expression": iterable_expression,
                    "block": block,
                    "if_expression": if_expression,
                }).toDict()
        
        middle_expression: DictRepr | None = None
        last_expression  : DictRepr | None = None

        if self.next.type == LexerTokenType.SEMI_COLON:
            self.advance()
            middle_expression = self.Expression()
            self.advance()
            last_expression = self.Statement()

        if has_paren:
            self.consume(LexerTokenType.RIGHT_PARENTHESIS)

        block = self.BlockStatement()
        return doToken(ParserTokenType.FOR_STATEMENT, {
            "start_expression"  : start_expression,
            "middle_expression": middle_expression,
            "last_expression"  : last_expression,
            "block": block,
        }).toDict()

    def helper_FunDeclaration(self):
        identifier = self.Identifier()
        self.consume(LexerTokenType.LEFT_PARENTHESIS)
        args: list[DictRepr] = []
        has_defaults = False
        i = 1
        min_argc: int = 0
        while self.next.type != LexerTokenType.RIGHT_PARENTHESIS:
            statement = self.Statement()
            if not has_defaults:
                assert statement['type'] in {
                    ParserTokenType.DECLARATION_UNDEFINED,
                    ParserTokenType.DECLARATION_TYPED_VAR
                }, powang_error_syntax('fun declaration', "Invalid argument expression", [
                    "Expected a variable declaration",
                    f"but {TokenToString(statement['type'])} was encountered"
                ])
                if statement['type'] == ParserTokenType.DECLARATION_TYPED_VAR:
                    has_defaults = True
                else:
                    min_argc += 1
            elif statement['type'] == ParserTokenType.DECLARATION_UNDEFINED:
                raise powang_throw(powang_error_format('LOGIC', 'fun arguments expression', f"Missing default value", [
                    f"expected argument {i} to have a default value",
                    "this is not the case..."
                ]))
            else:
                assert statement['type'] in {
                    ParserTokenType.DECLARATION_TYPED_VAR
                }, powang_error_syntax('fun declaration', "Invalid argument expression", [
                    "Expected a variable declaration with default value",
                    f"but {TokenToString(statement['type'])} was encountered"
                ])
            args.append(statement)
            if self.next.type == LexerTokenType.COMMA:
                self.advance()
            i += 1
        self.consume(LexerTokenType.RIGHT_PARENTHESIS)
        return_expr = None
        if self.next.type == LexerTokenType.COLON:
            self.advance()
            return_expr = self.Type()
        if self.next.type == LexerTokenType.LEFT_BRACE:
            block = self.BlockStatement()
        else:
            block = doToken(ParserTokenType.BLOCK_STATEMENT, None).toDict()
        return doToken(ParserTokenType.DECLARATION_FUN, {
            "identifier": identifier,
            "args": args,
            "min_argc": min_argc,
            "return": return_expr,
            "block": block
        }).toDict()

    def Expression(self):
        return self.Level_0_Expression()

    def Level_0_Expression(self):
        return self.helper_BinaryExpression(self. Level_1_Expression, (
            LexerTokenType.AND,
            LexerTokenType.OR,
        ))

    def Level_1_Expression(self):
        return self.helper_BinaryExpression(self.Level_2_Expression, (
            LexerTokenType.COMPARE_EQ,
            LexerTokenType.COMPARE_NEQ,
            LexerTokenType.COMPARE_LSS,
            LexerTokenType.COMPARE_GTR,
            LexerTokenType.COMPARE_GEQ,
            LexerTokenType.COMPARE_LEQ,
            LexerTokenType.COMPARE_EQ_TYPE,
            LexerTokenType.COMPARE_NEQ_TYPE,
        ))

    def Level_2_Expression(self):
        return self.helper_BinaryExpression(self.Level_3_Expression, (
            LexerTokenType.OPERATOR_PLUS,
            LexerTokenType.OPERATOR_MINUS
        ))

    def Level_3_Expression(self):
        return self.helper_BinaryExpression(self.Level_4_Expression, (
            LexerTokenType.STAR,
            LexerTokenType.SLASH
        ))
        
    def Level_4_Expression(self):
        return self.helper_BinaryExpression(self.UnaryExpression, (
            LexerTokenType.OPERATOR_CAST_AS,
        ))
        
    def helper_BinaryExpression(self, next_level: Callable[[], DictRepr], operators: tuple[LexerTokenType, ...]):
        left = next_level()
        while self.next and self.next.type in operators:
            operator = self.advance()
            typed = False
            if self.next.type == LexerTokenType.COLON:
                self.consume(self.next.type)
                typed = True
            right = next_level()
            left = doToken(ParserTokenType.BINARY_EXPRESSION, {
                "left": left,
                "operator": operator.toDict(),
                "right": right,
                "typed": typed,
            }).toDict()
        return left

    def UnaryExpression(self):
        return self.helper_UnaryExpression((
            LexerTokenType.EXCLAMATION,
            LexerTokenType.OPERATOR_MINUS,
            LexerTokenType.OPERATOR_PLUS,
            LexerTokenType.OPERATOR_SUMATORY,
            LexerTokenType.OPERATOR_INVERSE,
        ))

    def helper_UnaryExpression(self, operators: tuple[LexerTokenType, ...]):
        if self.next.type in operators:
            operator = self.consume(self.next.type)
            right = self.UnaryExpression()
            return doToken(ParserTokenType.UNARY_EXPRESSION, {
                "operator": operator.toDict(),
                "right": right
            }).toDict()
        return self.PostfixExpression()

    def PostfixExpression(self):
        expr = self.PrimaryExpression()
        while self.next is not None:
            if self.next.type == LexerTokenType.LEFT_PARENTHESIS:
                expr = self.CallExpression(expr)
            elif self.next.type == LexerTokenType.LEFT_BRACKET:
                expr = self.IndexExpression(expr)
            elif self.next.type == LexerTokenType.DOT:
                self.advance() # DOT
                # FAKE METHOD CALL
                if self.next.type == LexerTokenType.DOT:
                    self.advance() # DOT
                    expr = self.AccessExpression(expr)
                    call_expression = self.CallExpression(expr['value']['property'])
                    expr = doToken(
                        ParserTokenType.CALL_EXPRESSION, {
                            "callee"   : call_expression['value']['callee'],
                            "arguments": [expr['value']['target']] + call_expression['value']['arguments']
                        }
                    ).toDict()
                else:
                    expr = self.AccessExpression(expr)
                    if self.next.type == LexerTokenType.LEFT_PARENTHESIS:
                        call_expression = self.CallExpression(expr['value']['property'])
                        expr = doToken(
                            ParserTokenType.METHOD_CALL, {
                                "owner"    : expr['value']['target'],
                                "method"   : call_expression['value']['callee'],
                                "arguments": call_expression['value']['arguments'] 
                            }
                        ).toDict()
            else:
                break
        return expr

    def CallExpression(self, callee: DictRepr):
        self.consume(LexerTokenType.LEFT_PARENTHESIS)
        args: list[DictRepr] = []
        while self.next is not None and self.next.type != LexerTokenType.RIGHT_PARENTHESIS:
            args.append(self.Expression())
            # if self.next.type != LexerTokenType.RIGHT_PARENTHESIS:
            if self.next.type == LexerTokenType.COMMA:
                self.consume(LexerTokenType.COMMA)
        self.consume(LexerTokenType.RIGHT_PARENTHESIS)
        return doToken(ParserTokenType.CALL_EXPRESSION, {
            "callee": callee,
            "arguments": args
        }).toDict()
        
    def IndexExpression(self, target: DictRepr):
        self.consume(LexerTokenType.LEFT_BRACKET)
        index = self.Expression()
        self.consume(LexerTokenType.RIGHT_BRACKET)
        return doToken(ParserTokenType.INDEX_EXPRESSION, {
            "target": target,
            "index": index
        }).toDict()

    def AccessExpression(self, target: DictRepr):
        prop = self.Identifier()
        return doToken(ParserTokenType.ACCESS_EXPRESSION, {
            "target": target,
            "property": prop
        }).toDict()
        
    def Identifier(self):
        token = self.consume(LexerTokenType.IDENTIFIER)
        return token.toDict(token.value)
        
    def Keyword(self):
        token = self.consume(LexerTokenType.KEYWORD)
        return token.toDict()

    def VariableDeclaration(self, identifier: DictRepr):
        """
        `DECLARATION_TYPED_VAR => id: type = expr`  
        `DECLARATION_UNDEFINED => id: type`  
        `DECLARATION_INTERPRET => id := expr`  
        """
        if self.next.type == LexerTokenType.OPERATOR_ASSIGNMENT:
            self.consume(LexerTokenType.OPERATOR_ASSIGNMENT)
            expression = self.Expression()
            return doToken(ParserTokenType.DECLARATION_INTERPRET, {
                "identifier": identifier,
                "expression": expression,
            }).toDict()

        type = self.Type()
        if self.next.type == LexerTokenType.OPERATOR_ASSIGNMENT:
            self.consume(LexerTokenType.OPERATOR_ASSIGNMENT)
            expression = self.Expression()
            return doToken(ParserTokenType.DECLARATION_TYPED_VAR, {
                "identifier": identifier,
                "type": type,
                "expression": expression,
            }).toDict()

        return doToken(ParserTokenType.DECLARATION_UNDEFINED, {
            "identifier": identifier,
            "type": type,
        }).toDict()

    def Assignment(self, identifier: DictRepr):
        self.consume(LexerTokenType.OPERATOR_ASSIGNMENT)
        expression = self.Expression()
        return doToken(ParserTokenType.ASSIGNMENT, {
            "identifier": identifier,
            "expression": expression,
        }).toDict()

    def PrimaryExpression(self):
        match self.next.type:
            case LexerTokenType.SEMI_COLON:
                return DictRepr()
            case LexerTokenType.LEFT_PARENTHESIS:
                return self.ParenthesizedExpression()
            case LexerTokenType.LEFT_BRACKET:
                return self.ContainerExpression()
            case LexerTokenType.LEFT_BRACE:
                return self.BlockStatement()
            case LexerTokenType.IDENTIFIER:
                identifier = self.Identifier()
                if self.next.type == LexerTokenType.COLON:
                    self.consume(LexerTokenType.COLON)
                    return self.VariableDeclaration(identifier)
                return identifier
        return self.Literal('primary expression')

    def ParenthesizedExpression(self):
        self.consume(LexerTokenType.LEFT_PARENTHESIS)
        expression = self.Expression()
        self.consume(LexerTokenType.RIGHT_PARENTHESIS)
        return expression

    def ContainerExpression(self):
        self.consume(LexerTokenType.LEFT_BRACKET)
        
        elements: list = []
        is_map: bool = False
        while self.next is not None and self.next.type != LexerTokenType.RIGHT_BRACKET:
            expr = self.Expression()
            if is_map:
                expr = self.helper_KeyValuePair(expr)
            elif self.next.type == LexerTokenType.RIGHT_ARROW:
                assert len(elements) == 0, powang_error_syntax('Container Expression', 'Trying to do a mix up of array and map', [
                    "the array has elements before pair key-value appeared"
                ])
                is_map = True
                expr = self.helper_KeyValuePair(expr)
            elements.append(expr)
            if self.next.type == LexerTokenType.COMMA:
                self.consume(LexerTokenType.COMMA)                
            # if self.next.type != LexerTokenType.RIGHT_BRACKET:
                
        self.consume(LexerTokenType.RIGHT_BRACKET)
        return doToken(ParserTokenType.ARRAY_EXPRESSION, {
            "elements": elements,
            "type": {
                True: PowangMap.type,
                False: PowangArray.type,
            }[is_map]
        }).toDict()

    def helper_getMultipleStatements(self, where: str, condition_token: LexerTokenType):
        statements: list[DictRepr] = []
        while self.next.type != condition_token:
            stmt = self.ExpressionStatement()
            assert stmt is not None, powang_error_syntax(where, "Reached end of file")
            statements.append(stmt)
        self.consume(condition_token)
        return statements

    def BlockStatement(self):
        self.consume(LexerTokenType.LEFT_BRACE)
        statements = self.helper_getMultipleStatements('block expression', LexerTokenType.RIGHT_BRACE)
        return doToken(ParserTokenType.BLOCK_STATEMENT, statements).toDict()

    def Type(self):
        weak = const = False

        # TODO: Try the walrus notation for the weak = True and const = True
        if self.next.type == LexerTokenType.ARROBA:
            self.advance('type prefix')
            weak = True

        type_identifier: str = self.Identifier()['value']

        if weak: assert type_identifier != PowangNova.type, powang_error_format(
            "LOGIC", 'type notation', "A nova type can't be weak", [
                "this has no sense"
        ])
            
        if self.next.type == LexerTokenType.EXCLAMATION:
            self.advance('type postfix')
            const = True

        if type_identifier in TYPE_ALIAS:
            alias = TYPE_ALIAS[type_identifier]
            if weak: assert not alias['weak'], powang_error_format('LOGIC', 'type notation', 'Weak notation in a weak type alias', [
                f"type alias {type_identifier} already refers to a weak {alias['value']}"
            ])
            weak = alias['weak']
            if const: assert not alias['CONST'], powang_error_format('LOGIC', 'type notation', 'Constant notation in a constant type lias', [
                f"type alias {type_identifier} already refers to a constant {alias['value']}"
            ])
            const = alias['weak']
            type_identifier = alias['value']
        
        return doToken(ParserTokenType.TYPE, {
            "value": type_identifier,
            "weak": weak,
            "const": const,    
            "reference": None # TODO
        }).toDict()

    def helper_KeyValuePair(self, key: DictRepr):
        self.consume(LexerTokenType.RIGHT_ARROW)
        value = self.Expression()
        return doToken(ParserTokenType.KEY_VALUE_PAIR, {
            "key": key,
            "value": value,
        }).toDict()

    def Literal(self, where: Optional[str] = None):
        assert self.next is not None, powang_error_syntax_unexpected_end(where, self.tokenizer)
        match self.next.type:
            case LexerTokenType.NOVA_LITERAL:
                return self.NovaLiteral()
            case LexerTokenType.BOOLEAN_LITERAL:
                return self.BooleanLiteral()
            case LexerTokenType.INTEGER_LITERAL:
                return self.IntegerLiteral()
            case LexerTokenType.FLOATING_LITERAL:
                return self.FloatingNumberLiteral()
            case LexerTokenType.STRING_LITERAL:
                return self.StringLiteral()
        raise powang_throw(powang_error_syntax_unexpected_token(
            where,
            LexerTokenType.toStr(self.next.type),
            'literal',
        ))

    def NovaLiteral(self):
        token = self.consume(LexerTokenType.NOVA_LITERAL)
        return token.toDict(None)

    def BooleanLiteral(self):
        token = self.consume(LexerTokenType.BOOLEAN_LITERAL)
        return token.toDict({
            'true': True,
            'false': False,
        }[token.value])

    def IntegerLiteral(self):
        token = self.consume(LexerTokenType.INTEGER_LITERAL)
        return token.toDict(int(token.value))

    def FloatingNumberLiteral(self):
        token = self.consume(LexerTokenType.FLOATING_LITERAL)
        return token.toDict(float(token.value))

    def StringLiteral(self):
        token = self.consume(LexerTokenType.STRING_LITERAL)
        token.value = token.value.encode('utf-8').decode('unicode_escape')
        return token.toDict(token.value)

    def advance(self, where: Optional[str] = None):
        return self.consume(self.next.type, where)

    def consume(self, token_type: LexerTokenType, where: Optional[str] = None):
        token = self.next
        assert token is not None, powang_error_syntax_unexpected_end(None, self.tokenizer)

        if token.type != token_type:
            raise powang_throw(powang_error_syntax_unexpected_token(
                where,
                f"{LexerTokenType.toStr(token.type)}",
                f"{LexerTokenType.toStr(token_type)}",
            ))

        self.next = self.tokenizer.getNextToken()
        return token

    @staticmethod
    def simulate_Assignment(target: DictRepr, expr: DictRepr):
        return doToken(ParserTokenType.ASSIGNMENT, {
            "target": target,
            "expression": expr
        }).toDict()

    @staticmethod
    def simulate_Identifier(value: str):
        return doToken(LexerTokenType.IDENTIFIER, value).toDict()
    
    @staticmethod
    def simulate_Type(identifier: str, weak: bool, const: bool):
        return doToken(ParserTokenType.TYPE, {
            'value': identifier,
            'weak': weak,
            'const': const,
        }).toDict()