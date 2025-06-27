from .lexer import *
from .powang_types import *

TYPES: set[str] = {
    PowangNova.type,
    PowangSome.type,
    PowangInteger.type,
    PowangNumber.type,
    PowangBoolean.type,
    PowangString.type,
    PowangContainer.type,
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
        if self.next.type == LexerTokenType.IDENTIFIER:
            identifier = self.Identifier()

            match self.next.type:
                case LexerTokenType.COLON:
                    self.consume(LexerTokenType.COLON)
                    return self.VariableDeclaration(identifier)
                case LexerTokenType.OPERATOR_ASSIGNMENT:
                    return self.Assignment(identifier)
                case LexerTokenType.LEFT_PARENTHESIS:
                    return self.CallExpression(identifier)
            return identifier
        if self.next.type == LexerTokenType.KEYWORD:
            keyword = self.Keyword()
            # TODO: Implement IF, FOR, ELSE, ...
        return self.AdditionExpression()

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

        expression = self.Expression()
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

    def Expression(self):
        return self.AdditionExpression()

    def AdditionExpression(self):
        return self.GenericBinaryExpression(self.MultiplicationExpression, LexerTokenType.OPERATOR_ADDITION)

    def MultiplicationExpression(self):
        return self.GenericBinaryExpression(self.PrimaryExpression, LexerTokenType.OPERATOR_MULTIPLICATION)

    def GenericBinaryExpression(self, primary: Callable[(...), DictRepr], operator_type: LexerTokenType):
        left = primary()
        while self.next is not None and self.next.type == operator_type:
            operator = self.consume(operator_type)
            right = primary()
            left = doToken(ParserTokenType.BINARY_EXPRESSION, {
                'left': left,
                'operator': operator.toDict(),
                'right': right
            }).toDict()
        return left

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
                    return self.VariableDeclaration(identifier);
                if self.next.type == LexerTokenType.LEFT_PARENTHESIS:
                    return self.CallExpression(identifier)
                return identifier
        return self.Literal()

    def ParenthesizedExpression(self):
        self.consume(LexerTokenType.LEFT_PARENTHESIS)
        expression = self.Expression()
        self.consume(LexerTokenType.RIGHT_PARENTHESIS)
        return expression

    def ContainerExpression(self):
        self.consume(LexerTokenType.LEFT_BRACKET)
        elements = []
        while self.next is not None and self.next.type != LexerTokenType.RIGHT_BRACKET:
            elements.append(self.Expression())
        self.consume(LexerTokenType.RIGHT_BRACKET)
        return doToken(ParserTokenType.LIST_EXPRESSION, elements).toDict()

    def CallExpression(self, callee: DictRepr):
        self.consume(LexerTokenType.LEFT_PARENTHESIS)
        args = []
        while self.next is not None and self.next.type != LexerTokenType.RIGHT_PARENTHESIS:
            args.append(self.Expression())
        self.consume(LexerTokenType.RIGHT_PARENTHESIS)
        return doToken(ParserTokenType.CALL_EXPRESSION, {
            "callee": callee,
            "arguments": args
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
        assert self.next.type == LexerTokenType.IDENTIFIER, powang_error_syntax_unexpected_token(
            LexerTokenType.toStr(self.next.type),
            "Type Identifier",
            None
        )
        type = self.Identifier()['value']
        assert type in TYPES, powang_error_identifier_type(None, type)
        if self.next.type == LexerTokenType.EXCLAMATION:
            self.consume(LexerTokenType.EXCLAMATION)
            return doToken(ParserTokenType.WEAK_TYPE, {
                "value": type,
                "weak": True
            }).toDict()
        return doToken(ParserTokenType.TYPE, {
            "value": type,
            "weak": False    
        }).toDict()

    def TypedIdentifier(self):
        identifier = self.Identifier()
        self.consume(LexerTokenType.COLON)
        type = self.Type()
        return doToken(ParserTokenType.PAIR_TYPE_IDENTIFIER, {
            'identifier': identifier,
            'type': type,
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
                return self.FloatingLiteral()
            case LexerTokenType.STRING_LITERAL:
                return self.StringLiteral()
            case LexerTokenType.FMT_STRING_LITERAL:
                return self.FormatStringLiteral()
        raise powang_throw(powang_error_syntax_unexpected_token(
            LexerTokenType.toStr(self.next.type),
            'Literal',
            None
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

    def FloatingLiteral(self):
        token = self.consume(LexerTokenType.FLOATING_LITERAL)
        return token.toDict(float(token.value))

    def StringLiteral(self):
        token = self.consume(LexerTokenType.STRING_LITERAL)
        return token.toDict(token.value)

    def FormatStringLiteral(self):
        token = self.consume(LexerTokenType.FMT_STRING_LITERAL)
        return token.toDict(token.value)

    def Identifier(self):
        if self.next.type == LexerTokenType.NOVA_LITERAL:
            token = self.consume(LexerTokenType.NOVA_LITERAL)
        else:
            token = self.consume(LexerTokenType.IDENTIFIER)
        return token.toDict(token.value)

    def consume(self, token_type: LexerTokenType, where: Optional[str] = None):
        token = self.next
        assert token is not None, powang_error_syntax_unexpected_end(None, self.tokenizer)

        if token.type != token_type:
            raise powang_throw(powang_error_syntax_unexpected_token(
                f"{LexerTokenType.toStr(token.type)}",
                f"{LexerTokenType.toStr(token_type)}",
                where
            ))

        self.next = self.tokenizer.getNextToken()
        return token
