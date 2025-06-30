from .lexer import *
from .powang_types import *

TYPES: set[str] = {
    PowangNova.type,
    PowangSome.type,
    PowangInteger.type,
    PowangNumber.type,
    PowangBoolean.type,
    PowangString.type,
    PowangArray.type,
    PowangMap.type,
    PowangUserType.type,
}

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
        expression = self.Statement()
        if expression == {} or expression['type'] != TokenToString(ParserTokenType.BLOCK_STATEMENT):
            self.consume(LexerTokenType.SEMI_COLON)
        return expression

    def Statement(self):
        expr = self.Expression()

        # Si el próximo token es "=", esto es una asignación
        if self.next.type == LexerTokenType.OPERATOR_ASSIGNMENT:
            self.consume(LexerTokenType.OPERATOR_ASSIGNMENT)
            value = self.Expression()

            return doToken(ParserTokenType.ASSIGNMENT, {
                "target": expr,
                "expression": value
            }).toDict()

        return expr

    def Expression(self):
        return self.Level_1_Expression()

    def Level_1_Expression(self):
        return self.helper_BinaryExpression(self.Level_2_Expression, (
            LexerTokenType.OPERATOR_PLUS,
            LexerTokenType.OPERATOR_MINUS
        ))

    def Level_2_Expression(self):
        return self.helper_BinaryExpression(self.Level_3_Expresion, (
            LexerTokenType.STAR,
            LexerTokenType.SLASH
        ))

    def Level_3_Expresion(self):
        return self.helper_BinaryExpression(self.UnaryExpression, (
            LexerTokenType.OPERATOR_CAST_AS,
        ))

    def helper_BinaryExpression(self, next_level: Callable[[], DictRepr], operators: tuple[LexerTokenType, ...]):
        left = next_level()
        while self.next and self.next.type in operators:
            operator = self.consume(self.next.type)
            right = next_level()
            left = doToken(ParserTokenType.BINARY_EXPRESSION, {
                "left": left,
                "operator": operator.toDict(),
                "right": right
            }).toDict()
        return left

    def UnaryExpression(self):
        return self.helper_UnaryExpression((
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
                expr = self.AccessExpression(expr) 
            else:
                break
        return expr

    def CallExpression(self, callee: DictRepr):
        self.consume(LexerTokenType.LEFT_PARENTHESIS)
        args = []
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
        self.consume(LexerTokenType.DOT)
        prop = self.Identifier()
        return doToken(ParserTokenType.ACCESS_EXPRESSION, {
            "target": target,
            "property": prop
        }).toDict()
        
    def Identifier(self):
        if self.next.type == LexerTokenType.NOVA_LITERAL:
            token = self.consume(LexerTokenType.NOVA_LITERAL)
        else:
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
        return self.Literal()


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
            elif self.next.type == LexerTokenType.ARROW:
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

    def BlockStatement(self):
        self.consume(LexerTokenType.LEFT_BRACE)
        statements = []
        while self.next.type != LexerTokenType.RIGHT_BRACE:
            stmt = self.ExpressionStatement()
            if stmt is not None:
                statements.append(stmt)
        self.consume(LexerTokenType.RIGHT_BRACE)
        return doToken(ParserTokenType.BLOCK_STATEMENT, statements).toDict()

    def Type(self):
        weak = False
        const = False
        if self.next.type == LexerTokenType.ARROBA:
            self.consume(LexerTokenType.ARROBA)
            weak = True
            
        type = self.Identifier()['value']
        assert type in TYPES, powang_error_identifier_type(None, type)
        if self.next.type == LexerTokenType.EXCLAMATION:
            self.consume(LexerTokenType.EXCLAMATION)
            const = True
        return doToken(ParserTokenType.TYPE, {
            "value": type,
            "weak": weak,
            "const": const,    
        }).toDict()

    def TypedIdentifier(self):
        identifier = self.Identifier()
        self.consume(LexerTokenType.COLON)
        type = self.Type()
        return doToken(ParserTokenType.PAIR_TYPE_IDENTIFIER, {
            'identifier': identifier,
            'type': type,
        }).toDict()

    def helper_KeyValuePair(self, key: DictRepr):
        self.consume(LexerTokenType.ARROW)
        value = self.Expression()
        return doToken(ParserTokenType.KEY_VALUE_PAIR, {
            "key": key,
            "value": value,
        }).toDict()

    def Literal(self):
        assert self.next is not None, powang_error_syntax_unexpected_end(None, self.tokenizer)
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
            None,
            LexerTokenType.toStr(self.next.type),
            'Literal',
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
