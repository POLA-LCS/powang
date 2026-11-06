from .lexer import *
from .powang_types import *
from .state import get_state

from collections.abc import Iterator, MutableMapping
from pathlib import Path
import copy

NATI_TYPES: set[str] = {
    PowangNova.type   ,
    PowangSome.type   ,
    PowangInteger.type,
    PowangNumber.type ,
    PowangBoolean.type,
    PowangString.type ,
    PowangArray.type  ,
    PowangMap.type    ,
    PowangErrorValue.type,
    'tup',
}


class _PathsProxy(MutableMapping):
    """Compatibility view over the active state's ``paths`` dict.

    ``PATHS['RELATIVE']`` used to be a process-global dict. Keeping a small
    mapping facade lets old call sites keep the same syntax, while the actual
    mutable data lives on ``InterpreterState.paths``. The proxy stores nothing
    itself, so it cannot become shared mutable state again.
    """

    def _paths(self) -> dict[str, Path]:
        return get_state().paths

    def __getitem__(self, key: str) -> Path:
        return self._paths()[key]

    def __setitem__(self, key: str, value: Path) -> None:
        self._paths()[key] = value

    def __delitem__(self, key: str) -> None:
        del self._paths()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._paths())

    def __len__(self) -> int:
        return len(self._paths())

    def __contains__(self, key: object) -> bool:
        return key in self._paths()

    def get(self, key: str, default=None):
        return self._paths().get(key, default)

    def __repr__(self) -> str:
        return repr(self._paths())


PATHS: MutableMapping[str, Path] = _PathsProxy()

class Parser:
    def __init__(self, data: str, source_path: Path | str | None = None):
        self.data = data
        self.source_path = Path(source_path).resolve() if source_path is not None else None
        self.tokenizer = Tokenizer(data)
        self.next = self.tokenizer.getNextToken()
        ## Type tables belong to the run that is parsing, never to the module
        ## object, so an alias from one embedded run is invisible to the next.
        state = get_state()
        self.type_alias: dict[str, DictRepr] = state.type_alias
        self.user_types: set[str] = state.user_types
        self._synthetic_counter: int = 0
        self._consts: dict[str, DictRepr] = {}


    def parse(self):
        return self.Program()

    def Program(self):
        body: list[DictRepr] = []
        while self.next.type != LexerTokenType.END_OF_FILE:
            stmt = self.ExpressionStatement(top_level=True)
            if stmt is not None:
                body.append(stmt)
        return body

    def ExpressionStatement(self, top_level: bool = False):
        if self.next.type == LexerTokenType.END_OF_FILE:
            return None
        if self.next.type == LexerTokenType.KEYWORD:
            keyword = self.next.value
            if keyword == 'export':
                if not top_level:
                    raise powang_throw(powang_error_syntax(
                        'export declaration',
                        "export is only allowed at the top level of a module",
                        ["move the declaration out of the nested block"],
                    ))
                self.advance() # export
                if self.next.type == LexerTokenType.KEYWORD:
                    assert self.next.value in {'fun', 'type', 'extern'}, powang_error_syntax(
                        'export declaration',
                        f"export cannot be applied to {self.next.value}",
                        ["export supports fun, type, extern fun and variable declarations"],
                    )
                else:
                    assert self.next.type == LexerTokenType.IDENTIFIER, powang_error_syntax(
                        'export declaration',
                        "Expected a declaration after export",
                        [
                            f"but {LexerTokenType.toStr(self.next.type)} was encountered",
                        ],
                    )
                exported_statement = self.ExpressionStatement()
                assert exported_statement is not None, powang_error_syntax(
                    'export declaration', "Reached end of file",
                )
                assert exported_statement['type'] in {
                    ParserTokenType.DECLARATION_FUN,
                    ParserTokenType.DECLARATION_UNDEFINED,
                    ParserTokenType.DECLARATION_TYPED_VAR,
                    ParserTokenType.DECLARATION_INTERPRET,
                    ParserTokenType.TYPE_DECLARATION,
                    ParserTokenType.EXTERN_REFERENCE,
                }, powang_error_syntax(
                    'export declaration',
                    f"cannot export a {TokenToString(exported_statement['type'])}",
                )
                exported_statement['exported'] = True
                return exported_statement
            if keyword == 'spawn':
                ## `spawn` is an expression prefix, so a bare statement uses
                ## the normal expression-statement path instead of the
                ## statement-keyword dispatch below.
                expression = self.Statement()
                self.consume(LexerTokenType.SEMI_COLON)
                return expression
            self.consume(LexerTokenType.KEYWORD)
            match keyword:
                case 'if':
                    return self.helper_IfStatement()
                case 'try':
                    return self.helper_TryStatement()
                case 'catch' | 'finally':
                    raise powang_throw(powang_error_syntax(
                        'expression statement',
                        f"Unexpected keyword: {keyword}",
                        ["catch and finally must follow a try block"],
                    ))
                case 'for':
                    return self.helper_ForStatement()
                case 'match':
                    return self.helper_MatchStatement()
                case 'const':
                    return self.helper_ConstDeclaration()
                case 'fun':
                    return self.helper_FunDeclaration()
                case 'return':
                    expression = self.Expression()
                    if self.next.type == LexerTokenType.SEMI_COLON:
                        self.advance() # consume the optional trailing semicolon
                    return doToken(ParserTokenType.RETURN_EXPRESSION, expression).toDict()
                case 'type':
                    identifier = self.Identifier()
                    if self.next.type == LexerTokenType.KEYWORD and self.next.value == 'enum':
                        self.advance()
                        return self.helper_EnumDeclaration(identifier)
                    if self.next.type == LexerTokenType.RIGHT_ARROW:
                        self.advance()
                        type = self.Type()
                        self.type_alias[identifier['value']] = type['value']
                        return None
                    return self.helper_TypeObjectDeclaration(identifier)
                case 'use':
                    return self.helper_UseModule()
                case 'extern':
                    return self.helper_ExternSignature()
                case _:
                    raise powang_throw(powang_error_development('expression statement', f"{keyword} not implemented yet."))
        else:
            expression = self.Statement()
            self.consume(LexerTokenType.SEMI_COLON)
            return expression

    def helper_ExternSignature(self):
        if self.isNextKeyword('fun'):
            self.advance()
            powang_mapping = self.helper_FunDeclaration(allow_body=False)
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
            module_kind = 'name'
            module_spec = self.Identifier()['value']
        elif self.next.type == LexerTokenType.STRING_LITERAL:
            module_kind = 'path'
            module_spec = self.StringLiteral()['value']
        else:
            raise powang_throw(powang_error_syntax(
                'use statement',
                "Expected a module name or a path string",
                [
                    f"but {LexerTokenType.toStr(self.next.type)} was encountered",
                ],
            ))

        alias: str | None = None
        wildcard: bool = False
        if self.next.type == LexerTokenType.OPERATOR_CAST_AS:
            self.advance() # as
            if self.next.type == LexerTokenType.STAR:
                self.advance() # *
                wildcard = True
            elif self.next.type == LexerTokenType.IDENTIFIER:
                alias = self.Identifier()['value']
            else:
                raise powang_throw(powang_error_syntax(
                    'use statement',
                    "Expected an alias or '*' after 'as'",
                    [
                        f"but {LexerTokenType.toStr(self.next.type)} was encountered",
                    ],
                ))

        self.consume(LexerTokenType.SEMI_COLON)
        return doToken(ParserTokenType.USE_EXPRESSION, {
            'kind': module_kind,
            'name': module_spec,
            'alias': alias,
            'wildcard': wildcard,
            'base': str(self.source_path) if self.source_path is not None else None,
        }).toDict()

    def helper_TypeObjectDeclaration(self, identifier: DictRepr, is_signature: bool = False):
        assert identifier['value'] not in NATI_TYPES, powang_error_redefined(
            TokenToString(ParserTokenType.TYPE_DECLARATION),
            identifier['value'], [
                "a powang native type"
            ]
        )
        assert identifier['value'] not in self.type_alias, powang_error_redefined(
            TokenToString(ParserTokenType.TYPE_DECLARATION),
            identifier['value'], [
                f"a type alias for {self.type_alias[identifier['value']]['value']}"
            ]
        )
        assert identifier['value'] not in {'true', 'false'}, powang_error_redefined(
            TokenToString(ParserTokenType.TYPE_DECLARATION),
            identifier['value'], [
                f"which is a literal bool value"
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

    def helper_EnumDeclaration(self, identifier: DictRepr):
        assert identifier['value'] not in NATI_TYPES, powang_error_redefined(
            TokenToString(ParserTokenType.TYPE_DECLARATION),
            identifier['value'], [
                "a powang native type"
            ]
        )
        self.consume(LexerTokenType.LEFT_BRACE)
        variants: list[str] = []
        while self.next.type != LexerTokenType.RIGHT_BRACE:
            variant_name = self.Identifier()['value']
            assert variant_name not in variants, powang_error_redefined(
                TokenToString(ParserTokenType.TYPE_DECLARATION),
                variant_name, [
                    f"duplicate variant in enum {identifier['value']}"
                ]
            )
            variants.append(variant_name)
            if self.next.type == LexerTokenType.COMMA:
                self.advance()
            elif self.next.type != LexerTokenType.RIGHT_BRACE:
                raise powang_throw(powang_error_syntax(
                    'enum declaration', "Expected ',' or '}'", [
                        f"but {TokenToString(self.next.type)} was encountered",
                    ]))
        self.consume(LexerTokenType.RIGHT_BRACE)
        return doToken(ParserTokenType.TYPE_DECLARATION, {
            'identifier' : identifier,
            'properties' : None,
            'methods'    : None,
            'is_enum'    : True,
            'variants'   : variants,
        }).toDict()

    def DestructurePattern(self):
        self.consume(LexerTokenType.LEFT_BRACKET, 'destructuring pattern')
        entries: list[DictRepr] = []
        while self.next.type != LexerTokenType.RIGHT_BRACKET:
            identifier = self.Identifier()
            entry_type: DictRepr | None = None
            reference = False
            if self.next.type == LexerTokenType.COLON:
                self.advance('destructuring binding')
                if self.next.type == LexerTokenType.AMPERSAND:
                    self.advance('destructuring reference')
                    reference = True
                    if self.next.type not in {
                        LexerTokenType.COMMA,
                        LexerTokenType.RIGHT_BRACKET,
                    }:
                        entry_type = self.Type()
                else:
                    entry_type = self.Type()
            entries.append({
                'identifier': identifier,
                'type': entry_type,
                'reference': reference,
            })
            if self.next.type == LexerTokenType.COMMA:
                self.advance()
            else:
                break
        self.consume(LexerTokenType.RIGHT_BRACKET, 'destructuring pattern')

        pattern = doToken(ParserTokenType.DESTRUCTURE_PATTERN, {
            'entries': entries,
            'group_type': None,
            'group_reference': False,
        }).toDict()

        if self.next.type == LexerTokenType.COLON:
            state = self._saveParserState()
            self.advance()
            if self.next.type == LexerTokenType.OPERATOR_ASSIGNMENT:
                self._restoreParserState(state)
            else:
                group_reference = False
                group_type: DictRepr | None = None
                if self.next.type == LexerTokenType.AMPERSAND:
                    self.advance('destructuring reference')
                    group_reference = True
                    if self.next.type not in {
                        LexerTokenType.OPERATOR_ASSIGNMENT,
                        LexerTokenType.SEMI_COLON,
                        LexerTokenType.RIGHT_ARROW,
                    }:
                        group_type = self.Type()
                else:
                    group_type = self.Type()
                pattern['value']['group_type'] = group_type
                pattern['value']['group_reference'] = group_reference
        return pattern

    @staticmethod
    def _destructure_is_typed(pattern: DictRepr) -> bool:
        group_type = pattern['value'].get('group_type')
        if group_type is not None:
            return True
        for entry in pattern['value'].get('entries', []):
            if entry.get('type') is None:
                return False
        return True

    @staticmethod
    def _destructure_operator(pattern: DictRepr) -> str:
        return '=' if Parser._destructure_is_typed(pattern) else ':='

    def DestructureDeclaration(self):
        pattern = self.DestructurePattern()
        if self.next.type == LexerTokenType.COLON:
            self.advance()
            self.consume(LexerTokenType.OPERATOR_ASSIGNMENT, 'destructuring declaration')
            operator = ':='
        elif self.next.type == LexerTokenType.OPERATOR_ASSIGNMENT:
            self.advance()
            operator = '='
        else:
            raise powang_throw(powang_error_syntax(
                'destructuring declaration',
                'Expected := or = after the destructuring pattern',
            ))

        if operator == ':=' and self._destructure_is_typed(pattern):
            raise powang_throw(powang_error_syntax(
                'destructuring declaration',
                'Use = when every binding has an explicit type',
            ))
        if operator == '=' and not self._destructure_is_typed(pattern):
            raise powang_throw(powang_error_syntax(
                'destructuring declaration',
                'Use := when at least one binding infers its type',
            ))

        expression = self.Expression()
        return doToken(ParserTokenType.DESTRUCTURE_DECLARATION, {
            'pattern': pattern,
            'expression': expression,
            'operator': operator,
        }).toDict()

    def Statement(self):
        if self.next.type == LexerTokenType.LEFT_BRACKET:
            state = self._saveParserState()
            is_destructure = False
            try:
                self.DestructurePattern()
                is_destructure = self.next.type in {
                    LexerTokenType.COLON,
                    LexerTokenType.OPERATOR_ASSIGNMENT,
                }
            except Exception:
                is_destructure = False
            self._restoreParserState(state)
            if is_destructure:
                return self.DestructureDeclaration()

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
    
    def helper_TryStatement(self):
        """`try { ... } (catch [name] { ... })* (finally { ... })?`"""
        try_block = self.BlockStatement()

        catches: list[DictRepr] = []
        while self.isNextKeyword('catch'):
            self.advance()
            catch_name: DictRepr | None = None
            if self.next.type == LexerTokenType.IDENTIFIER:
                catch_name = self.Identifier()
            catch_block = self.BlockStatement()
            catches.append({
                "name": catch_name,
                "block": catch_block,
            })

        finally_block: DictRepr | None = None
        if self.isNextKeyword('finally'):
            self.advance()
            finally_block = self.BlockStatement()

        if not catches and finally_block is None:
            raise powang_throw(powang_error_syntax(
                'try statement',
                'try requires at least one catch or finally block',
            ))

        return doToken(ParserTokenType.TRY_STATEMENT, {
            "block": try_block,
            "catches": catches,
            "finally_block": finally_block,
        }).toDict()

    def _saveParserState(self):
        return (self.tokenizer.position, self.tokenizer.row, self.next)

    def _restoreParserState(self, state) -> None:
        self.tokenizer.position, self.tokenizer.row, self.next = state

    def Condition(self):
        """Accept a declaration or a normal expression in an `if` condition."""
        state = self._saveParserState()
        statement = self.Statement()
        if statement['type'] in {
            ParserTokenType.DECLARATION_INTERPRET,
            ParserTokenType.DECLARATION_TYPED_VAR,
            ParserTokenType.DECLARATION_UNDEFINED,
        }:
            return statement
        self._restoreParserState(state)
        return self.Expression()

    def helper_IfStatement(self):
        if self.next.type == LexerTokenType.LEFT_PARENTHESIS:
              expr = self.ParenthesizedExpression()
        else: expr = self.Condition()
            
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
        
    def MatchPattern(self):
        if self.next.type == LexerTokenType.RIGHT_ARROW:
            ## `case >> expr` is a catch-all wildcard.
            return {'kind': 'wildcard', 'value': None, 'type': None}
        if self.next.type == LexerTokenType.IDENTIFIER and self.next.value == '_':
            self.advance('match wildcard')
            return {'kind': 'wildcard', 'value': None, 'type': None}
        if self.next.type in {
            LexerTokenType.INTEGER_LITERAL,
            LexerTokenType.FLOATING_LITERAL,
            LexerTokenType.STRING_LITERAL,
            LexerTokenType.BOOLEAN_LITERAL,
            LexerTokenType.NOVA_LITERAL,
            LexerTokenType.INTERPOLATED_STRING_LITERAL,
        }:
            return {'kind': 'literal', 'value': self.Literal('match pattern'), 'type': None}
        if self.next.type == LexerTokenType.IDENTIFIER:
            # A dotted name such as Color.RED is a literal pattern, not a
            # binding. Peek ahead without consuming the identifier.
            saved_position = self.tokenizer.position
            saved_row = self.tokenizer.row
            saved_next = self.next
            self.advance('match pattern')
            is_access = self.next.type == LexerTokenType.DOT
            self.tokenizer.position = saved_position
            self.tokenizer.row = saved_row
            self.next = saved_next
            if is_access:
                return {'kind': 'literal', 'value': self.PostfixExpression(), 'type': None}
            identifier = self.Identifier()
            type_node: DictRepr | None = None
            if self.next.type == LexerTokenType.COLON:
                self.advance()
                type_node = self.Type()
            return {'kind': 'binding', 'value': identifier, 'type': type_node}
        raise powang_throw(powang_error_syntax(
            'match pattern',
            'Expected a literal, a binding or _',
            [f'but {LexerTokenType.toStr(self.next.type)} was encountered'],
        ))

    def helper_MatchExpression(self, subject: DictRepr):
        self.consume(LexerTokenType.LEFT_BRACE, 'match expression')
        cases: list[DictRepr] = []
        while self.isNextKeyword('case'):
            self.advance()
            pattern = self.MatchPattern()
            guard: DictRepr | None = None
            if self.isNextKeyword('if'):
                self.advance()
                guard = self.Expression()
            self.consume(LexerTokenType.RIGHT_ARROW, 'match case')
            if self.next.type == LexerTokenType.LEFT_BRACE:
                block = self.BlockStatement()
                cases.append({
                    'pattern': pattern,
                    'guard': guard,
                    'block': block,
                    'is_expression': False,
                })
            else:
                value = self.Expression()
                cases.append({
                    'pattern': pattern,
                    'guard': guard,
                    'value': value,
                    'is_expression': True,
                })
        self.consume(LexerTokenType.RIGHT_BRACE, 'match expression')
        return doToken(ParserTokenType.MATCH_EXPRESSION, {
            'subject': subject,
            'cases': cases,
        }).toDict()

    def helper_MatchStatement(self):
        subject = self.Expression()
        self.consume(LexerTokenType.LEFT_BRACE, 'match statement')
        cases: list[DictRepr] = []
        while self.isNextKeyword('case'):
            self.advance()
            pattern = self.MatchPattern()
            guard: DictRepr | None = None
            if self.isNextKeyword('if'):
                self.advance()
                guard = self.Expression()
            self.consume(LexerTokenType.RIGHT_ARROW, 'match case')
            if self.next.type == LexerTokenType.LEFT_BRACE:
                block = self.BlockStatement()
            else:
                statement = self.ExpressionStatement()
                assert statement is not None, powang_error_syntax('match case', 'Reached end of file')
                block = doToken(ParserTokenType.BLOCK_STATEMENT, [statement]).toDict()
            cases.append({
                'pattern': pattern,
                'guard': guard,
                'block': block,
            })
        self.consume(LexerTokenType.RIGHT_BRACE, 'match statement')
        return doToken(ParserTokenType.MATCH_STATEMENT, {
            'subject': subject,
            'cases': cases,
        }).toDict()

    def helper_ForStatement(self):
        has_paren = False
        if self.next.type == LexerTokenType.LEFT_PARENTHESIS:
            self.consume(LexerTokenType.LEFT_PARENTHESIS)
            has_paren = True

        destructure_pattern: DictRepr | None = None
        if self.next.type == LexerTokenType.LEFT_BRACKET:
            state = self._saveParserState()
            try:
                candidate = self.DestructurePattern()
                if self.next.type == LexerTokenType.RIGHT_ARROW:
                    destructure_pattern = candidate
                    synthetic_identifier = doToken(
                        LexerTokenType.IDENTIFIER,
                        f'__powang_iter_{self._synthetic_counter}',
                    ).toDict()
                    self._synthetic_counter += 1
                    start_expression = doToken(ParserTokenType.DECLARATION_UNDEFINED, {
                        "identifier": synthetic_identifier,
                        "type": doToken(ParserTokenType.TYPE, {
                            'value': PowangSome.type,
                            'const': False,
                            'weak': False,
                            'reference': None,
                        }).toDict(),
                        "inferred": True,
                    }).toDict()
                else:
                    self._restoreParserState(state)
                    start_expression = self.Statement()
            except Exception:
                self._restoreParserState(state)
                start_expression = self.Statement()
        else:
            start_expression = self.Statement()

        original_start = start_expression

        if self.next.type == LexerTokenType.RIGHT_ARROW:
            if start_expression['type'] not in {
                ParserTokenType.DECLARATION_UNDEFINED,
                ParserTokenType.DECLARATION_TYPED_VAR
            }:
                ## Bare identifier head (`for x >> arr {}`): implicitly declare
                ## the iterator as weakly-typed `some` so any element binds.
                assert start_expression['type'] == LexerTokenType.IDENTIFIER, \
                    powang_error_syntax('for each expression', 'iterator must be a variable declaration or an identifier')
                start_expression = doToken(ParserTokenType.DECLARATION_UNDEFINED, {
                    "identifier": start_expression,
                    "type": doToken(ParserTokenType.TYPE, {
                        'value': PowangSome.type,
                        'const': False,
                        'weak': False,
                        'reference': None,
                    }).toDict(),
                    "inferred": True,
                }).toDict()

            self.advance()
            iterable_expression = self.Expression()

            ## `for i >> start >> end` and `for i >> start >> step >> end`
            ## are range loops. They desugar to the existing C-style for node.
            if self.next.type == LexerTokenType.RIGHT_ARROW:
                self.advance()
                second_expression = self.Expression()
                step_expression: DictRepr | None = None
                end_expression: DictRepr = second_expression
                if self.next.type == LexerTokenType.RIGHT_ARROW:
                    self.advance()
                    step_expression = second_expression
                    end_expression = self.Expression()

                if original_start['type'] == LexerTokenType.IDENTIFIER:
                    iterator_identifier = original_start
                    iterator_type = None
                elif original_start['type'] in {
                    ParserTokenType.DECLARATION_UNDEFINED,
                    ParserTokenType.DECLARATION_TYPED_VAR,
                }:
                    iterator_identifier = original_start['value']['identifier']
                    iterator_type = original_start['value']['type']
                else:
                    raise powang_throw(powang_error_syntax(
                        'for range expression',
                        'iterator must be a variable declaration or an identifier',
                    ))

                if iterator_type is None:
                    start_declaration = doToken(ParserTokenType.DECLARATION_INTERPRET, {
                        "identifier": iterator_identifier,
                        "expression": iterable_expression,
                    }).toDict()
                else:
                    start_declaration = doToken(ParserTokenType.DECLARATION_TYPED_VAR, {
                        "identifier": iterator_identifier,
                        "type": iterator_type,
                        "expression": iterable_expression,
                    }).toDict()

                condition = doToken(ParserTokenType.BINARY_EXPRESSION, {
                    "left": iterator_identifier,
                    "operator": doToken(LexerTokenType.COMPARE_LSS, '<').toDict(),
                    "right": end_expression,
                    "typed": False,
                }).toDict()
                step_value = step_expression if step_expression is not None else \
                    doToken(LexerTokenType.INTEGER_LITERAL, 1).toDict()
                increment_expression = doToken(ParserTokenType.BINARY_EXPRESSION, {
                    "left": iterator_identifier,
                    "operator": doToken(LexerTokenType.OPERATOR_PLUS, '+').toDict(),
                    "right": step_value,
                    "typed": False,
                }).toDict()
                increment = doToken(ParserTokenType.ASSIGNMENT, {
                    "target": iterator_identifier,
                    "expression": increment_expression,
                }).toDict()

                if has_paren:
                    self.consume(LexerTokenType.RIGHT_PARENTHESIS)
                block = self.BlockStatement()
                return doToken(ParserTokenType.FOR_STATEMENT, {
                    "start_expression": start_declaration,
                    "middle_expression": condition,
                    "last_expression": increment,
                    "block": block,
                }).toDict()

            if_expression: DictRepr | None = None
            if self.next.type == LexerTokenType.KEYWORD:
                assert self.next.value == 'if', powang_error_syntax('for each expression', f"{self.next.value} is not a valid keyword in this context", [
                    "for each last expression only accepts if keyword"
                ])
                self.advance()
                if_expression = self.Expression()
            block = self.BlockStatement()
            if destructure_pattern is not None:
                destructure_declaration = doToken(ParserTokenType.DESTRUCTURE_DECLARATION, {
                    'pattern': destructure_pattern,
                    'expression': start_expression['value']['identifier'],
                    'operator': self._destructure_operator(destructure_pattern),
                }).toDict()
                block['value'] = [destructure_declaration] + block['value']
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
            self.consume(LexerTokenType.SEMI_COLON, 'for statement')
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

    def helper_ConstDeclaration(self):
        identifier = self.Identifier()
        if self.next.type == LexerTokenType.COLON:
            self.advance()
            self.Type()
        self.consume(LexerTokenType.OPERATOR_ASSIGNMENT, 'const declaration')
        expression = self.Expression()
        self._consts[identifier['value']] = expression
        if self.next.type == LexerTokenType.SEMI_COLON:
            self.advance()
        return None

    def helper_FunDeclaration(self, allow_body: bool = True):
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
        elif allow_body and self.next.type == LexerTokenType.RIGHT_ARROW:
            assert return_expr is not None, powang_error_syntax(
                'function body',
                'Expression-bodied functions require a return type',
                ['add a return type after the closing parenthesis'],
            )
            self.advance('function body')
            expression = self.Expression()
            block = doToken(ParserTokenType.BLOCK_STATEMENT, [
                doToken(ParserTokenType.RETURN_EXPRESSION, expression).toDict()
            ]).toDict()
            if self.next.type == LexerTokenType.SEMI_COLON:
                self.advance()
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
        return self.Level_Pipeline()

    def Level_Pipeline(self):
        return self.helper_BinaryExpression(self.Level_Coalesce, (
            LexerTokenType.PIPELINE,
        ))

    def Level_Coalesce(self):
        return self.helper_BinaryExpression(self.Level_0_Expression, (
            LexerTokenType.COALESCE,
        ))

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
            LexerTokenType.SLASH,
            LexerTokenType.PERCENT,
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
        if self.next.type == LexerTokenType.AMPERSAND:
            self.advance('reference expression')
            target = self.Identifier()
            return doToken(ParserTokenType.REFERENCE_EXPRESSION, {
                "target": target,
            }).toDict()
        if self.next.type == LexerTokenType.KEYWORD and self.next.value == 'spawn':
            self.advance('spawn expression')
            spawned = self.UnaryExpression()
            assert spawned['type'] == ParserTokenType.CALL_EXPRESSION, powang_error_syntax(
                'spawn expression',
                "spawn expects a function call",
                [
                    "write it as: spawn function_name(args)",
                    f"but {TokenToString(spawned['type'])} was encountered",
                ],
            )
            return doToken(ParserTokenType.SPAWN_EXPRESSION, {
                "call": spawned,
            }).toDict()
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
            if self.next.type == LexerTokenType.QUESTION_MARK:
                ## Postfix error-propagation operator. It binds tighter than
                ## call/index/access: `find(id)?` unwraps the call result.
                self.advance('postfix unwrap')
                expr = doToken(ParserTokenType.POSTFIX_UNWRAP, {
                    "expression": expr,
                }).toDict()
            elif self.next.type == LexerTokenType.LEFT_PARENTHESIS:
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
            elif self.next.type == LexerTokenType.SAFE_ACCESS:
                self.advance('safe access')
                expr = doToken(ParserTokenType.SAFE_ACCESS_EXPRESSION, {
                    "target": expr,
                    "property": self.Identifier(),
                }).toDict()
            elif self.next.type == LexerTokenType.KEYWORD and self.next.value == 'match':
                self.advance('match expression')
                expr = self.helper_MatchExpression(expr)
            else:
                break
        return expr

    def CallExpression(self, callee: DictRepr):
        self.consume(LexerTokenType.LEFT_PARENTHESIS)
        args: list[DictRepr] = []
        while self.next is not None and self.next.type != LexerTokenType.RIGHT_PARENTHESIS:
            if self.next.type == LexerTokenType.IDENTIFIER:
                state = self._saveParserState()
                name = self.Identifier()
                if self.next.type == LexerTokenType.RIGHT_ARROW:
                    self.advance()
                    value = self.Expression()
                    args.append(doToken(ParserTokenType.NAMED_ARGUMENT, {
                        'name': name,
                        'value': value,
                    }).toDict())
                    if self.next.type == LexerTokenType.COMMA:
                        self.consume(LexerTokenType.COMMA)
                    continue
                self._restoreParserState(state)
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
            case LexerTokenType.DOT:
                saved_position = self.tokenizer.position
                saved_row = self.tokenizer.row
                saved_next = self.next
                self.advance('tuple literal')  # consume the leading dot
                is_tuple = self.next is not None and self.next.type == LexerTokenType.LEFT_BRACKET
                # restore
                self.tokenizer.position = saved_position
                self.tokenizer.row = saved_row
                self.next = saved_next
                if is_tuple:
                    self.advance('tuple literal')  # consume the leading dot
                    return self.helper_TupleExpression()
                return self.Literal('primary expression')
            case LexerTokenType.IDENTIFIER:
                identifier = self.Identifier()
                if self.next.type == LexerTokenType.COLON:
                    self.consume(LexerTokenType.COLON)
                    return self.VariableDeclaration(identifier)
                if identifier['value'] in self._consts:
                    return copy.deepcopy(self._consts[identifier['value']])
                return identifier
        return self.Literal('primary expression')

    def helper_TupleExpression(self):
        self.consume(LexerTokenType.LEFT_BRACKET)
        elements: list = []
        while self.next is not None and self.next.type != LexerTokenType.RIGHT_BRACKET:
            elements.append(self.Expression())
            if self.next.type == LexerTokenType.COMMA:
                self.advance()
        self.consume(LexerTokenType.RIGHT_BRACKET)
        return doToken(ParserTokenType.TUPLE_EXPRESSION, {
            "elements": elements,
        }).toDict()

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
        error_union = False
        reference = False
        element_type: Optional[DictRepr] = None

        if self.next.type == LexerTokenType.AMPERSAND:
            self.advance('reference type')
            reference = True

        if self.next.type == LexerTokenType.ARROBA:
            self.advance('type prefix')
            weak = True

        type_identifier: str = self.Identifier()['value']

        generics: list = []
        if type_identifier == 'tup' and self.next.type == LexerTokenType.LEFT_BRACKET:
            self.consume(LexerTokenType.LEFT_BRACKET)
            while self.next.type != LexerTokenType.RIGHT_BRACKET:
                generics.append(self.Type())
                if self.next.type == LexerTokenType.COMMA:
                    self.advance()
                elif self.next.type != LexerTokenType.RIGHT_BRACKET:
                    raise powang_throw(powang_error_syntax('tuple type', "Expected ',' or ']' in tup[...]", [
                        f"but {TokenToString(self.next.type)} was encountered",
                    ]))
            self.consume(LexerTokenType.RIGHT_BRACKET)

        ## `arr[element]` is the typed form. Bare `arr` is sugar for
        ## `arr[any]`, where `any` resolves to the gradual `some` type.
        if type_identifier == PowangArray.type and self.next is not None and self.next.type == LexerTokenType.LEFT_BRACKET:
            self.consume(LexerTokenType.LEFT_BRACKET, 'arr element type')
            element_type = self.Type()
            self.consume(LexerTokenType.RIGHT_BRACKET, 'arr element type')

        if reference and weak:
            raise powang_throw(powang_error_format(
                "LOGIC", 'type notation', "A reference can't be weak", [
                    "references point at an existing variable"
                ]))

        if weak: assert type_identifier != PowangNova.type, powang_error_format(
            "LOGIC", 'type notation', "A nova type can't be weak", [
                "this has no sense"
        ])
            
        if self.next.type == LexerTokenType.EXCLAMATION:
            self.advance('type postfix')
            const = True

        if reference and const:
            raise powang_throw(powang_error_format(
                "LOGIC", 'type notation', "A reference can't be constant", [
                    "references point at an existing variable"
                ]))

        if type_identifier in self.type_alias:
            alias = self.type_alias[type_identifier]
            if weak: assert not alias['weak'], powang_error_format('LOGIC', 'type notation', 'Weak notation in a weak type alias', [
                f"type alias {type_identifier} already refers to a weak {alias['value']}"
            ])
            weak = alias['weak']
            if const: assert not alias['const'], powang_error_format('LOGIC', 'type notation', 'Constant notation in a constant type lias', [
                f"type alias {type_identifier} already refers to a constant {alias['value']}"
            ])
            const = alias['const']
            if element_type is None and alias.get('element_type') is not None:
                element_type = alias['element_type']
            type_identifier = alias['value']

        ## `any` is the gradual unknown used by bare `arr` sugar.
        if type_identifier == 'any':
            type_identifier = PowangSome.type

        ## A trailing `?` marks an error-union return annotation:
        ## `fun find(id: int): map? { ... }` may also return `error`.
        if self.next.type == LexerTokenType.QUESTION_MARK:
            self.advance('type error union')
            error_union = True

        return doToken(ParserTokenType.TYPE, {
            "value": type_identifier,
            "weak": weak,
            "const": const,
            "error_union": error_union,
            "reference": reference,
            "element_type": element_type,
            "generics": generics,
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
            case LexerTokenType.INTERPOLATED_STRING_LITERAL:
                return self.InterpolatedStringLiteral()
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
        token.value = self._processStringEscapes(token.value)
        return token.toDict(token.value)

    @staticmethod
    def _processStringEscapes(value: str) -> str:
        ## Manual escape processing: unicode_escape would re-decode the raw
        ## UTF-8 bytes as latin-1 and corrupt non-ASCII characters.
        ESCAPES: dict[str, str] = {'n': '\n', 't': '\t', 'r': '\r', '\\': '\\', '"': '"', '0': '\0'}
        processed: list[str] = []
        i = 0
        while i < len(value):
            char = value[i]
            if char == '\\' and i + 1 < len(value) and value[i + 1] in ESCAPES:
                processed.append(ESCAPES[value[i + 1]])
                i += 2
            else:
                processed.append(char)
                i += 1
        return ''.join(processed)

    def InterpolatedStringLiteral(self):
        token = self.consume(LexerTokenType.INTERPOLATED_STRING_LITERAL)
        raw = token.value
        parts: list[dict] = []
        text: list[str] = []

        def flush_text() -> None:
            if text:
                parts.append({
                    'kind': 'text',
                    'value': self._processStringEscapes(''.join(text)),
                })
                text.clear()

        i = 0
        while i < len(raw):
            char = raw[i]
            if char == '\\' and i + 1 < len(raw):
                text.append(char)
                text.append(raw[i + 1])
                i += 2
                continue
            if char == '{':
                if i + 1 < len(raw) and raw[i + 1] == '{':
                    text.append('{')
                    i += 2
                    continue
                flush_text()
                depth = 1
                j = i + 1
                in_string = False
                escaped = False
                while j < len(raw):
                    current = raw[j]
                    if in_string:
                        if escaped:
                            escaped = False
                        elif current == '\\':
                            escaped = True
                        elif current == '"':
                            in_string = False
                    else:
                        if current == '"':
                            in_string = True
                        elif current == '{':
                            depth += 1
                        elif current == '}':
                            depth -= 1
                            if depth == 0:
                                break
                    j += 1
                if j >= len(raw):
                    raise powang_throw(powang_error_syntax(
                        'interpolated string',
                        'Unclosed interpolation',
                        ['add a closing brace'],
                    ))
                expression_source = raw[i + 1:j]
                sub_parser = Parser(expression_source)
                sub_parser._consts = self._consts
                expression = sub_parser.Expression()
                if sub_parser.next.type != LexerTokenType.END_OF_FILE:
                    raise powang_throw(powang_error_syntax(
                        'interpolated string',
                        'Unexpected token in interpolation',
                        [f'but {LexerTokenType.toStr(sub_parser.next.type)} was encountered'],
                    ))
                parts.append({'kind': 'expression', 'value': expression})
                i = j + 1
                continue
            if char == '}':
                if i + 1 < len(raw) and raw[i + 1] == '}':
                    text.append('}')
                    i += 2
                    continue
                raise powang_throw(powang_error_syntax(
                    'interpolated string',
                    'Unexpected closing brace',
                    ['use }} for a literal brace'],
                ))
            text.append(char)
            i += 1

        flush_text()
        return doToken(ParserTokenType.INTERPOLATED_STRING, {'parts': parts}).toDict()

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
            'error_union': False,
            'reference': None,
        }).toDict()