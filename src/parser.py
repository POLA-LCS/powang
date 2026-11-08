from .lexer import *
from .powang_types import *
from .error import require
from .state import get_state

from collections.abc import Iterator, MutableMapping
from pathlib import Path
import copy

NATI_TYPES: set[str] = {
    PowangNova.type   ,
    PowangAnyType.type   ,
    PowangInteger.type,
    PowangNumber.type ,
    PowangBoolean.type,
    PowangString.type ,
    PowangArray.type  ,
    PowangMap.type    ,
    PowangSet.type    ,
    PowangHandle.type ,
    PowangProject.type,
    PowangErrorValue.type,
    PowangFileStream.type,
    PowangTask.type,
    'tup',
    'obj',
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
        self.state = state
        self.type_alias: dict[str, DictRepr] = state.type_alias
        self.user_types: set[str] = state.user_types
        ## Types declared by this file. The parser uses the set only for
        ## disambiguation (`Name[...]` versus `name[index]`), never for
        ## semantic decisions.
        self.declared_types: set[str] = set()
        self._synthetic_counter: int = 0
        self._consts: dict[str, DictRepr] = {}
        self._type_member_context: bool = False


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
                    require(self.next.value in {'fun', 'type', 'extern'}, lambda: powang_error_syntax(
                        'export declaration',
                        f"export cannot be applied to {self.next.value}",
                        ["export supports fun, type, extern fun and variable declarations"],
                    ))
                else:
                    require(self.next.type == LexerTokenType.IDENTIFIER, lambda: powang_error_syntax(
                        'export declaration',
                        "Expected a declaration after export",
                        [
                            f"but {LexerTokenType.toStr(self.next.type)} was encountered",
                        ],
                    ))
                exported_statement = self.ExpressionStatement()
                require(exported_statement is not None, lambda: powang_error_syntax(
                    'export declaration', "Reached end of file",
                ))
                require(exported_statement['type'] in {
                    ParserTokenType.DECLARATION_FUN,
                    ParserTokenType.DECLARATION_UNDEFINED,
                    ParserTokenType.DECLARATION_TYPED_VAR,
                    ParserTokenType.DECLARATION_INTERPRET,
                    ParserTokenType.TYPE_DECLARATION,
                    ParserTokenType.EXTERN_REFERENCE,
                }, lambda: powang_error_syntax(
                    'export declaration',
                    f"cannot export a {TokenToString(exported_statement['type'])}",
                ))
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
                case 'module':
                    identifier = self.Identifier()
                    self.consume(LexerTokenType.SEMI_COLON)
                    return doToken(ParserTokenType.MODULE_DECLARATION, {
                        'identifier': identifier,
                    }).toDict()
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
                case 'loop':
                    return self.helper_LoopStatement()
                case 'break' | 'continue':
                    return self.helper_LoopControl(keyword)
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
            require(powang_mapping['value']['block']['value'] is None, lambda: powang_error_syntax('extern function', "Expected function signature but function definition was encountered"))
        else:
            require(self.isNextKeyword('type'), lambda: powang_error_syntax('extern signature', "There's only external functions and types", [
                f"encountered: {TokenToString(self.next.type)}"
            ]))
            self.advance()
            identifier = self.Identifier()
            powang_mapping = self.helper_TypeObjectDeclaration(identifier, True)
            require(powang_mapping['value']['properties'] is None, lambda: powang_error_syntax('extern type', "Expected type signature but type definition was encountered"))
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
        require(identifier['value'] not in NATI_TYPES, lambda: powang_error_redefined(
            TokenToString(ParserTokenType.TYPE_DECLARATION),
            identifier['value'], [
                "a powang native type"
            ]
        ))
        require(identifier['value'] not in self.type_alias, lambda: powang_error_redefined(
            TokenToString(ParserTokenType.TYPE_DECLARATION),
            identifier['value'], [
                f"a type alias for {self.type_alias[identifier['value']]['value']}"
            ]
        ))
        require(identifier['value'] not in {'true', 'false'}, lambda: powang_error_redefined(
            TokenToString(ParserTokenType.TYPE_DECLARATION),
            identifier['value'], [
                f"which is a literal bool value"
            ]
        ))
        
        if is_signature:
            return doToken(ParserTokenType.TYPE_DECLARATION, {
                'identifier' : identifier,
                'properties' : None,
                'methods'    : None,
                'access_default': None,
                'type_parameters': [],
            }).toDict()  

        access_default: Optional[str] = None
        type_parameters: list[str] = []
        for _ in range(2):
            if access_default is None and self.next.type == LexerTokenType.OPERATOR_SUMATORY:
                access_default = '+'
                self.advance('type access default')
                continue
            if access_default is None and self.next.type == LexerTokenType.OPERATOR_INVERSE:
                access_default = '-'
                self.advance('type access default')
                continue
            if not type_parameters and self.next.type == LexerTokenType.LEFT_BRACKET:
                self.consume(LexerTokenType.LEFT_BRACKET, 'type parameters')
                while self.next.type != LexerTokenType.RIGHT_BRACKET:
                    parameter = self.Identifier()['value']
                    if parameter in type_parameters:
                        raise powang_throw(powang_error_redefined(
                            'type parameter', parameter,
                        ))
                    type_parameters.append(parameter)
                    if self.next.type == LexerTokenType.COMMA:
                        self.advance()
                    elif self.next.type != LexerTokenType.RIGHT_BRACKET:
                        raise powang_throw(self._syntax_at_current(powang_error_syntax(
                            'type parameters', "Expected ',' or ']' in type parameters",
                        )))
                self.consume(LexerTokenType.RIGHT_BRACKET)
                continue
            break

        properties: list[tuple[bool, DictRepr]] = []
        methods   : list[tuple[bool, DictRepr]] = []
        constructor_members: list[DictRepr] = []
        explicit_constructor: tuple[bool, DictRepr] | None = None
        ignored_constructor_members: bool = False
        ignored_member_token: DictRepr | None = None

        self.consume(LexerTokenType.LEFT_BRACE)
        while self.next.type != LexerTokenType.RIGHT_BRACE:
            pipe_token = None
            pipe = False
            if self.next.type == LexerTokenType.PIPE:
                pipe_token = self.next
                pipe = True
                self.advance('constructor member')

            access_token = None
            explicit_access: Optional[str] = None
            if self.next.type == LexerTokenType.OPERATOR_PLUS:
                access_token = self.next
                explicit_access = '+'
                self.advance('member access')
            elif self.next.type == LexerTokenType.OPERATOR_MINUS:
                access_token = self.next
                explicit_access = '-'
                self.advance('member access')
            elif access_default is None:
                raise powang_throw(self._syntax_at_current(powang_error_syntax(
                    'type declaration',
                    f"type '{identifier['value']}' has no default access",
                    [
                        "declare the type as type T[+] or type T[-]",
                        "or prefix every member with + or -",
                    ],
                )))

            if self.next.type == LexerTokenType.KEYWORD and self.next.value == 'const':
                if pipe:
                    raise powang_throw(self._syntax_at_current(powang_error_syntax(
                        'constructor member',
                        "the const keyword cannot be combined with |",
                        [
                            "declare a write-once member as name: type! instead",
                        ],
                    )))
                raise powang_throw(self._syntax_at_current(powang_error_syntax(
                    'type member',
                    "the const keyword is not supported inside a type body",
                    ["declare a write-once member as name: type!"],
                )))

            effective_access = explicit_access if explicit_access is not None else access_default
            is_public: bool = effective_access == '+'

            if access_token is not None and access_default is not None \
                    and explicit_access == access_default:
                self.state.warn(
                    f"unnecessary access specifier '{explicit_access}' in type '{identifier['value']}'",
                    access_token.line,
                    access_token.column,
                    access_token.column + 1 if access_token.column is not None else None,
                    'PW201',
                )

            previous_member_context = self._type_member_context
            self._type_member_context = True
            try:
                statement = self.ExpressionStatement()
            finally:
                self._type_member_context = previous_member_context
            if statement is None:
                raise powang_throw(self._syntax_at_current(
                    powang_error_syntax('type declaration', "Reached end of file")
                ))
            statement.setdefault('value', {})
            if isinstance(statement['value'], dict):
                statement['value']['explicit_access'] = explicit_access
                statement['value']['constructor_member'] = pipe

            if statement['type'] in {
                ParserTokenType.DECLARATION_UNDEFINED,
                ParserTokenType.DECLARATION_TYPED_VAR
            }:
                if pipe:
                    member_type = statement['value'].get('type')
                    if statement['type'] == ParserTokenType.DECLARATION_TYPED_VAR and \
                            self._type_node_is_const(member_type):
                        raise powang_throw(self._syntax_at_current(powang_error_syntax(
                            'constructor member',
                            "a write-once member cannot have both an initializer and |",
                            [
                                "remove the initializer so the constructor performs the single write",
                            ],
                        )))
                    constructor_members.append(statement)
                properties.append((is_public, statement))
            elif statement['type'] == ParserTokenType.DECLARATION_FUN:
                if pipe:
                    raise powang_throw(self._syntax_at_current(powang_error_syntax(
                        'constructor member',
                        "a method cannot be marked as a constructor parameter",
                    )))
                fun_identifier = statement['value']['identifier']
                fun_return     = statement['value']['return']
                if fun_identifier['value'] == CONSTRUCTOR_METHOD_NAME:
                    if not is_public:
                        raise powang_throw(powang_error_format(
                            'LOGIC', 'constructor declaration', "Type constructor must be public"
                        ))
                    explicit_constructor = (is_public, statement)
                    # Sets the default constructor return type to the object type
                    if fun_return is None:
                        statement['value']['return'] = self.simulate_Type(identifier['value'], False, False)
                    else:
                        # Check if the return type matches the object type
                        if fun_return['value']['value'] != identifier['value']:
                            raise powang_throw(powang_error_format(
                                'LOGIC', 'constructor declaration', 'Return type must be the object type', [
                                    f'expected {identifier['value']}',
                                    f'but {fun_return['value']['value']} was encountered'
                                ]
                            ))
                    
                    # Return "this" default return
                    statement['value']['block']['value'].append(
                        doToken(ParserTokenType.RETURN_EXPRESSION, self.simulate_Identifier('this')
                    ).toDict())
                methods.append((is_public, statement))
            else:
                raise powang_throw(powang_error_syntax(
                    'type declaration',
                    "Expected a member declaration",
                    [
                        f"but {TokenToString(statement['type'])} was encountered",
                    ],
                ))
        self.advance()

        member_names: set[str] = set()
        for member in constructor_members:
            member_name = member['value']['identifier']['value']
            if member_name in member_names:
                raise powang_throw(powang_error_redefined(
                    'constructor member', member_name, [
                        "constructor parameter names must be unique",
                    ]
                ))
            member_names.add(member_name)

        if explicit_constructor is not None:
            constructor_statement = explicit_constructor[1]
            constructor_args = constructor_statement['value']['args']
            if constructor_members and len(constructor_args) == 0:
                ## Zero-parameter explicit constructor: body hook.
                constructor_statement['value']['args'] = self._constructor_arguments(
                    constructor_members
                )
                constructor_statement['value']['min_argc'] = sum(
                    1 for arg in constructor_statement['value']['args']
                    if arg['type'] == ParserTokenType.DECLARATION_UNDEFINED
                )
                constructor_statement['value']['block']['value'] = (
                    self._constructor_assignments(constructor_members)
                    + constructor_statement['value']['block']['value']
                )
            elif constructor_members:
                ignored_constructor_members = True
                ignored_member_token = constructor_members[0]['value']['identifier']
        elif constructor_members:
            methods.append((True, self._generated_constructor(identifier, constructor_members)))
        else:
            methods.append((True, doToken(ParserTokenType.DECLARATION_FUN, {
                'identifier': self.simulate_Identifier(CONSTRUCTOR_METHOD_NAME),
                'args': [],
                'min_argc': 0,
                'return': self.simulate_Type(identifier['value'], False, False),
                'block': doToken(ParserTokenType.BLOCK_STATEMENT, [
                    doToken(ParserTokenType.RETURN_EXPRESSION, self.simulate_Identifier('this')).toDict(),
                ]).toDict()
            }).toDict()))

        if ignored_constructor_members:
            self.state.warn(
                f"constructor members in type '{identifier['value']}' are ignored because an explicit constructor with parameters is declared",
                ignored_member_token.get('line') if isinstance(ignored_member_token, dict) else None,
                ignored_member_token.get('column') if isinstance(ignored_member_token, dict) else None,
                None,
                'PW202',
            )

        self.declared_types.add(identifier['value'])
        return doToken(ParserTokenType.TYPE_DECLARATION, {
            'identifier' : identifier,
            'properties' : properties,
            'methods'    : methods,
            'access_default': access_default,
            'type_parameters': type_parameters,
        }).toDict()

    def _type_node_is_const(self, type_node: Optional[DictRepr]) -> bool:
        if not isinstance(type_node, dict):
            return False
        inner = type_node.get('value')
        return isinstance(inner, dict) and bool(inner.get('const'))

    def _constructor_arguments(self, constructor_members: list[DictRepr]) -> list[DictRepr]:
        arguments: list[DictRepr] = []
        for member in constructor_members:
            member_value = member['value']
            ## Constructor parameters are always required: the member
            ## initializer, when present, runs before the constructor body and
            ## the generated assignment then overrides it.
            arguments.append(doToken(ParserTokenType.DECLARATION_UNDEFINED, {
                'identifier': copy.deepcopy(member_value['identifier']),
                'type': copy.deepcopy(member_value['type']),
            }).toDict())
        return arguments

    def _constructor_assignments(self, constructor_members: list[DictRepr]) -> list[DictRepr]:
        assignments: list[DictRepr] = []
        for member in constructor_members:
            member_name = member['value']['identifier']['value']
            target = doToken(ParserTokenType.ACCESS_EXPRESSION, {
                'target': self.simulate_Identifier('this'),
                'property': self.simulate_Identifier(member_name),
            }).toDict()
            assignments.append(self.simulate_Assignment(
                target, self.simulate_Identifier(member_name)
            ))
        return assignments

    def _generated_constructor(self, identifier: DictRepr,
                               constructor_members: list[DictRepr]) -> DictRepr:
        arguments = self._constructor_arguments(constructor_members)
        body = self._constructor_assignments(constructor_members)
        body.append(doToken(
            ParserTokenType.RETURN_EXPRESSION, self.simulate_Identifier('this')
        ).toDict())
        return doToken(ParserTokenType.DECLARATION_FUN, {
            'identifier': self.simulate_Identifier(CONSTRUCTOR_METHOD_NAME),
            'args': arguments,
            'min_argc': sum(
                1 for arg in arguments
                if arg['type'] == ParserTokenType.DECLARATION_UNDEFINED
            ),
            'return': self.simulate_Type(identifier['value'], False, False),
            'block': doToken(ParserTokenType.BLOCK_STATEMENT, body).toDict(),
        }).toDict()


    def helper_EnumDeclaration(self, identifier: DictRepr):
        require(identifier['value'] not in NATI_TYPES, lambda: powang_error_redefined(
            TokenToString(ParserTokenType.TYPE_DECLARATION),
            identifier['value'], [
                "a powang native type"
            ]
        ))
        self.consume(LexerTokenType.LEFT_BRACE)
        variants: list[str] = []
        while self.next.type != LexerTokenType.RIGHT_BRACE:
            variant_name = self.Identifier()['value']
            require(variant_name not in variants, lambda: powang_error_redefined(
                TokenToString(ParserTokenType.TYPE_DECLARATION),
                variant_name, [
                    f"duplicate variant in enum {identifier['value']}"
                ]
            ))
            variants.append(variant_name)
            if self.next.type == LexerTokenType.COMMA:
                self.advance()
            elif self.next.type != LexerTokenType.RIGHT_BRACE:
                raise powang_throw(powang_error_syntax(
                    'enum declaration', "Expected ',' or '}'", [
                        f"but {TokenToString(self.next.type)} was encountered",
                    ]))
        self.consume(LexerTokenType.RIGHT_BRACE)
        self.declared_types.add(identifier['value'])
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

    def _LoopLabel(self):
        if self.next.type == LexerTokenType.PIPE:
            self.advance('loop label')
            identifier = self.Identifier()
            self.consume(LexerTokenType.PIPE, 'loop label')
            return identifier['value']
        return None

    def helper_LoopStatement(self):
        label = self._LoopLabel()
        condition = None
        if self.next.type == LexerTokenType.KEYWORD and self.next.value == 'if':
            self.advance('loop condition')
            condition = self.Condition()
        block = self.BlockStatement()
        return doToken(ParserTokenType.LOOP_STATEMENT, {
            'label': label,
            'condition': condition,
            'block': block,
        }).toDict()

    def helper_LoopControl(self, keyword: str):
        label = None
        if self.next.type == LexerTokenType.IDENTIFIER:
            label = self.next.value
            self.advance('loop control label')
        if self.next.type == LexerTokenType.SEMI_COLON:
            self.advance()
        token_type = (
            ParserTokenType.BREAK_STATEMENT
            if keyword == 'break'
            else ParserTokenType.CONTINUE_STATEMENT
        )
        return doToken(token_type, {'label': label}).toDict()

    def helper_IfStatement(self):
        if self.next.type == LexerTokenType.LEFT_PARENTHESIS:
              expr = self.ParenthesizedExpression()
        else: expr = self.Condition()
            
        if self.next.type == LexerTokenType.LEFT_BRACE:
            block = self.BlockStatement()
        else:
            block = self.ExpressionStatement()
            require(block is not None, lambda: powang_error_syntax('if expression', "Reached end of file"))
            block = doToken(ParserTokenType.BLOCK_STATEMENT, [block]).toDict()
        
        else_block: DictRepr | None = None

        if self.isNextKeyword('else'):
            self.advance()
            if self.next.type == LexerTokenType.LEFT_BRACE:
                else_block = self.BlockStatement()
            else:
                else_block = self.ExpressionStatement()
                require(else_block is not None, lambda: powang_error_syntax('else expression', "Reached end of file"))
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
                require(statement is not None, lambda: powang_error_syntax('match case', 'Reached end of file'))
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
        label = self._LoopLabel()
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
                            'value': PowangAnyType.type,
                            'const': False,
                            'weak': False,
                            'reference': None,
                            'error_union': False,
                            'element_type': None,
                            'generics': [],
                            'variadic': False,
                            'alternatives': [],
                            'auto': False,
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
                require(start_expression['type'] == LexerTokenType.IDENTIFIER, lambda: powang_error_syntax('for each expression', 'iterator must be a variable declaration or an identifier'))
                start_expression = doToken(ParserTokenType.DECLARATION_UNDEFINED, {
                    "identifier": start_expression,
                    "type": doToken(ParserTokenType.TYPE, {
                        'value': PowangAnyType.type,
                        'const': False,
                        'weak': False,
                        'reference': None,
                        'error_union': False,
                        'element_type': None,
                        'generics': [],
                        'variadic': False,
                        'alternatives': [],
                        'auto': False,
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
                    "label": label,
                    "start_expression": start_declaration,
                    "middle_expression": condition,
                    "last_expression": increment,
                    "block": block,
                }).toDict()

            if_expression: DictRepr | None = None
            if self.next.type == LexerTokenType.KEYWORD:
                require(self.next.value == 'if', lambda: powang_error_syntax('for each expression', f"{self.next.value} is not a valid keyword in this context", [
                    "for each last expression only accepts if keyword"
                ]))
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
                "label": label,
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
            "label": label,
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
        instance_method = False
        if self.next.type == LexerTokenType.DOT:
            self.advance('instance method marker')
            instance_method = True
            identifier = self.Identifier()
        else:
            token = self.consume(LexerTokenType.IDENTIFIER)
            if token.value == 'this' and self.next.type == LexerTokenType.DOT:
                self.advance('instance method marker')
                instance_method = True
                identifier = self.Identifier()
            else:
                identifier = token.toDict(token.value)
                identifier['line'] = token.line
                identifier['column'] = token.column
        args: list[DictRepr] = []
        has_defaults = False
        i = 1
        min_argc: int = 0
        has_parameter_list = self.next.type == LexerTokenType.LEFT_PARENTHESIS
        if not has_parameter_list:
            if identifier['value'] != CONSTRUCTOR_METHOD_NAME or self.next.type != LexerTokenType.LEFT_BRACE:
                raise powang_throw(self._syntax_at_current(powang_error_syntax(
                    'fun declaration',
                    "Expected '(' after the function name",
                    [f"but {TokenToString(self.next.type)} was encountered"],
                )))
        else:
            self.consume(LexerTokenType.LEFT_PARENTHESIS)
        while has_parameter_list and self.next.type != LexerTokenType.RIGHT_PARENTHESIS:
            statement = self.Statement()
            if not has_defaults:
                require(statement['type'] in {
                    ParserTokenType.DECLARATION_UNDEFINED,
                    ParserTokenType.DECLARATION_TYPED_VAR
                }, lambda: powang_error_syntax('fun declaration', "Invalid argument expression", [
                    "Expected a variable declaration",
                    f"but {TokenToString(statement['type'])} was encountered"
                ]))
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
                require(statement['type'] in {
                    ParserTokenType.DECLARATION_TYPED_VAR
                }, lambda: powang_error_syntax('fun declaration', "Invalid argument expression", [
                    "Expected a variable declaration with default value",
                    f"but {TokenToString(statement['type'])} was encountered"
                ]))
            args.append(statement)
            if self.next.type == LexerTokenType.COMMA:
                self.advance()
            i += 1
        if has_parameter_list:
            self.consume(LexerTokenType.RIGHT_PARENTHESIS)
        return_expr = None
        if self.next.type == LexerTokenType.COLON:
            self.advance()
            return_expr = self.Type()
        if self.next.type == LexerTokenType.LEFT_BRACE:
            block = self.BlockStatement()
        elif allow_body and self.next.type == LexerTokenType.RIGHT_ARROW:
            require(return_expr is not None, lambda: powang_error_syntax(
                'function body',
                'Expression-bodied functions require a return type',
                ['add a return type after the closing parenthesis'],
            ))
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
            "block": block,
            "instance_method": instance_method,
        }).toDict()

    def Expression(self):
        return self.Level_Coalesce()

    def Level_Pipeline(self):
        return self.helper_BinaryExpression(self.Level_3_Expression, (
            LexerTokenType.PIPELINE,
            LexerTokenType.REFERENCE_PIPELINE,
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
        return self.helper_BinaryExpression(self.Level_Pipeline, (
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
            if operator.type == LexerTokenType.REFERENCE_PIPELINE:
                if left.get('type') != LexerTokenType.IDENTIFIER:
                    raise powang_throw(self._syntax_at_current(powang_error_syntax(
                        'reference pipeline',
                        "The left side of &> must be a variable",
                        ["write x &> function(...) instead"],
                    )))
                left = doToken(ParserTokenType.REFERENCE_EXPRESSION, {
                    'target': left,
                }).toDict()
                operator = LexerToken(LexerTokenType.PIPELINE, ':>', operator.line, operator.column)
            typed = False
            if self.next.type == LexerTokenType.COLON:
                self.consume(self.next.type)
                typed = True
            if operator.type in {
                LexerTokenType.COMPARE_EQ_TYPE,
                LexerTokenType.COMPARE_NEQ_TYPE,
                LexerTokenType.OPERATOR_CAST_AS,
            }:
                right = self.Type()
            else:
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
            require(spawned['type'] in {
                ParserTokenType.CALL_EXPRESSION,
                ParserTokenType.METHOD_CALL,
            }, lambda: powang_error_syntax(
                'spawn expression',
                "spawn expects a function or method call",
                [
                    "write it as: spawn function_name(args)",
                    "or: spawn receiver.method(args)",
                    f"but {TokenToString(spawned['type'])} was encountered",
                ],
            ))
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
                if expr.get('type') == LexerTokenType.IDENTIFIER:
                    type_reference = self._tryParameterizedTypeReference(expr)
                    if type_reference is not None:
                        expr = type_reference
                        continue
                expr = self.IndexExpression(expr)
            elif self.next.type == LexerTokenType.DOT:
                if expr.get('type') in {
                    LexerTokenType.IDENTIFIER,
                    ParserTokenType.TYPE_REFERENCE,
                } and self._dot_starts_instantiation():
                    expr = self.InstantiationExpression(expr)
                    continue
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

    def _dot_starts_instantiation(self) -> bool:
        state = self._saveParserState()
        try:
            self.advance('instantiation lookahead')
            return self.next.type == LexerTokenType.LEFT_BRACKET
        finally:
            self._restoreParserState(state)

    def _tryParameterizedTypeReference(self, identifier: DictRepr) -> Optional[DictRepr]:
        """Parse ``Name[types]`` only when ``.[`` follows, otherwise back off."""
        name = identifier.get('value')
        if not isinstance(name, str):
            return None
        if name not in NATI_TYPES and name not in self.declared_types and name not in self.type_alias:
            return None
        state = self._saveParserState()
        try:
            type_reference = self._parseTypeReference(name)
            if self.next.type != LexerTokenType.DOT:
                self._restoreParserState(state)
                return None
            if not self._dot_starts_instantiation():
                self._restoreParserState(state)
                return None
            return type_reference
        except Exception:
            self._restoreParserState(state)
            return None

    def _parseTypeReference(self, name: str) -> DictRepr:
        type_parameters: list[DictRepr] = []
        variadic = False
        if self.next.type == LexerTokenType.LEFT_BRACKET:
            self.consume(LexerTokenType.LEFT_BRACKET, 'type parameters')
            while self.next.type != LexerTokenType.RIGHT_BRACKET:
                if self.next.type == LexerTokenType.ELLIPSIS:
                    self.advance('variadic type reference')
                    variadic = True
                    break
                type_parameters.append(self.Type())
                if self.next.type == LexerTokenType.COMMA:
                    self.advance()
                elif self.next.type != LexerTokenType.RIGHT_BRACKET:
                    raise powang_throw(powang_error_syntax(
                        'type parameters', "Expected ',' or ']'", [
                            f"but {TokenToString(self.next.type)} was encountered",
                        ]))
            self.consume(LexerTokenType.RIGHT_BRACKET)
        return doToken(ParserTokenType.TYPE_REFERENCE, {
            'name': name,
            'type_parameters': type_parameters,
            'variadic': variadic,
        }).toDict()

    def InstantiationExpression(self, target: DictRepr) -> DictRepr:
        if target.get('type') == ParserTokenType.TYPE_REFERENCE:
            type_reference = copy.deepcopy(target['value'])
        else:
            type_reference = {'name': target['value'], 'type_parameters': []}
        type_name = type_reference['name']
        line = self.next.line if self.next is not None else None
        column = self.next.column if self.next is not None else None
        self.consume(LexerTokenType.DOT, 'instantiation')
        self.consume(LexerTokenType.LEFT_BRACKET, 'instantiation')

        arguments: list[DictRepr] = []
        named = False
        positional = False
        while self.next is not None and self.next.type != LexerTokenType.RIGHT_BRACKET:
            if type_name == PowangMap.type:
                value = self.Expression()
                if self.next.type == LexerTokenType.RIGHT_ARROW:
                    value = self.helper_KeyValuePair(value)
                arguments.append({'name': None, 'value': value})
                positional = True
            elif (type_name not in NATI_TYPES or type_name == 'Project') and self.next.type == LexerTokenType.IDENTIFIER:
                state = self._saveParserState()
                name_node = self.Identifier()
                if self.next.type == LexerTokenType.RIGHT_ARROW:
                    self.advance('named argument')
                    arguments.append({
                        'name': name_node['value'],
                        'value': self.Expression(),
                    })
                    named = True
                    if self.next.type == LexerTokenType.COMMA:
                        self.consume(LexerTokenType.COMMA)
                    continue
                self._restoreParserState(state)
                arguments.append({'name': None, 'value': self.Expression()})
                positional = True
            else:
                arguments.append({'name': None, 'value': self.Expression()})
                positional = True
            if self.next.type == LexerTokenType.COMMA:
                self.consume(LexerTokenType.COMMA)
        self.consume(LexerTokenType.RIGHT_BRACKET, 'instantiation')
        if named and positional:
            raise powang_throw(self._syntax_at_current(powang_error_syntax(
                'instantiation',
                "Named and positional arguments cannot be mixed",
                ["use all names or all positions, never both"],
            )))
        return doToken(ParserTokenType.INSTANTIATION, {
            'type_ref': type_reference,
            'arguments': arguments,
            'named': named,
            'line': line,
            'column': column,
        }).toDict()

    @staticmethod
    def _auto_type_node() -> DictRepr:
        return doToken(ParserTokenType.TYPE, {
            'value': 'auto',
            'weak': False,
            'const': False,
            'error_union': False,
            'reference': False,
            'element_type': None,
            'generics': [],
            'variadic': False,
            'alternatives': [],
            'auto': True,
            'line': None,
            'column': None,
        }).toDict()

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
        if self.next.type == LexerTokenType.RIGHT_ARROW:
            self.advance('slice')
            end = None if self.next.type == LexerTokenType.RIGHT_BRACKET else self.Expression()
            self.consume(LexerTokenType.RIGHT_BRACKET)
            return doToken(ParserTokenType.SLICE_EXPRESSION, {
                "target": target,
                "start": None,
                "end": end,
            }).toDict()
        index = self.Expression()
        if self.next.type == LexerTokenType.RIGHT_ARROW:
            self.advance('slice')
            end = None if self.next.type == LexerTokenType.RIGHT_BRACKET else self.Expression()
            self.consume(LexerTokenType.RIGHT_BRACKET)
            return doToken(ParserTokenType.SLICE_EXPRESSION, {
                "target": target,
                "start": index,
                "end": end,
            }).toDict()
        if self.next.type == LexerTokenType.COMMA:
            elements = [index]
            while self.next.type == LexerTokenType.COMMA:
                self.advance()
                elements.append(self.Expression())
            index = doToken(ParserTokenType.TUPLE_EXPRESSION, {
                "elements": elements,
            }).toDict()
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
        result = token.toDict(token.value)
        result['line'] = token.line
        result['column'] = token.column
        return result
        
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
            self._warn_single_tuple(identifier, expression)
            return doToken(ParserTokenType.DECLARATION_INTERPRET, {
                "identifier": identifier,
                "expression": expression,
            }).toDict()

        type = self.Type(pipe_can_start_member=self._type_member_context)
        if self.next.type == LexerTokenType.OPERATOR_ASSIGNMENT:
            self.consume(LexerTokenType.OPERATOR_ASSIGNMENT)
            expression = self.Expression()
            self._warn_single_tuple(identifier, expression)
            return doToken(ParserTokenType.DECLARATION_TYPED_VAR, {
                "identifier": identifier,
                "type": type,
                "expression": expression,
            }).toDict()

        return doToken(ParserTokenType.DECLARATION_UNDEFINED, {
            "identifier": identifier,
            "type": type,
        }).toDict()

    def _warn_single_tuple(self, identifier: DictRepr, expression: DictRepr) -> None:
        if not isinstance(expression, dict) or expression.get('type') != ParserTokenType.INSTANTIATION:
            return
        value = expression.get('value')
        if not isinstance(value, dict):
            return
        type_ref = value.get('type_ref')
        if not isinstance(type_ref, dict) or type_ref.get('name') != PowangTuple.type:
            return
        arguments = value.get('arguments')
        if not isinstance(arguments, list) or len(arguments) != 1:
            return
        name = identifier.get('value', 'value')
        self.state.warn(
            f"single-element tuple assigned to '{name}' has no advantage over the value itself, write {name} := <value> instead",
            identifier.get('line'),
            identifier.get('column'),
            None,
            'PW203',
        )

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
        return doToken(ParserTokenType.INSTANTIATION, {
            'type_ref': {
                'name': PowangTuple.type,
                'type_parameters': [self._auto_type_node() for _ in elements],
            },
            'arguments': [{'name': None, 'value': element} for element in elements],
            'named': False,
            'line': None,
            'column': None,
        }).toDict()

    def ParenthesizedExpression(self):
        self.consume(LexerTokenType.LEFT_PARENTHESIS)
        expression = self.Expression()
        self.consume(LexerTokenType.RIGHT_PARENTHESIS)
        return expression

    def ContainerExpression(self):
        self.consume(LexerTokenType.LEFT_BRACKET)

        if self.next is not None and self.next.type == LexerTokenType.RIGHT_ARROW:
            self.advance('empty map literal')
            if self.next is None or self.next.type != LexerTokenType.RIGHT_BRACKET:
                raise powang_throw(self._syntax_at_current(powang_error_syntax(
                    'map literal',
                    "[>>] is only the empty map literal",
                    ["write non-empty maps as [\"key\" >> value]"],
                )))
            self.consume(LexerTokenType.RIGHT_BRACKET)
            return doToken(ParserTokenType.INSTANTIATION, {
                'type_ref': {'name': PowangMap.type, 'type_parameters': []},
                'arguments': [],
                'named': False,
                'line': None,
                'column': None,
            }).toDict()

        if self.next is not None and self.next.type == LexerTokenType.SLASH:
            self.advance('set literal')
            elements: list = []
            while self.next is not None and self.next.type != LexerTokenType.RIGHT_BRACKET:
                elements.append(self.Expression())
                if self.next.type == LexerTokenType.COMMA:
                    self.consume(LexerTokenType.COMMA)
                elif self.next.type != LexerTokenType.RIGHT_BRACKET:
                    raise powang_throw(self._syntax_at_current(powang_error_syntax(
                        'set literal', "Expected ',' or ']' in set literal",
                    )))
            self.consume(LexerTokenType.RIGHT_BRACKET)
            return doToken(ParserTokenType.INSTANTIATION, {
                'type_ref': {
                    'name': PowangSet.type,
                    'type_parameters': [self._auto_type_node()],
                },
                'arguments': [{'name': None, 'value': element} for element in elements],
                'named': False,
                'line': None,
                'column': None,
            }).toDict()

        elements: list = []
        is_map: bool = False
        while self.next is not None and self.next.type != LexerTokenType.RIGHT_BRACKET:
            expr = self.Expression()
            if is_map:
                expr = self.helper_KeyValuePair(expr)
            elif self.next.type == LexerTokenType.RIGHT_ARROW:
                require(len(elements) == 0, lambda: powang_error_syntax('Container Expression', 'Trying to do a mix up of array and map', [
                    "the array has elements before pair key-value appeared"
                ]))
                is_map = True
                expr = self.helper_KeyValuePair(expr)
            elements.append(expr)
            if self.next.type == LexerTokenType.COMMA:
                self.consume(LexerTokenType.COMMA)                
            # if self.next.type != LexerTokenType.RIGHT_BRACKET:
                
        self.consume(LexerTokenType.RIGHT_BRACKET)
        if is_map:
            return doToken(ParserTokenType.INSTANTIATION, {
                'type_ref': {'name': PowangMap.type, 'type_parameters': []},
                'arguments': [{'name': None, 'value': element} for element in elements],
                'named': False,
                'line': None,
                'column': None,
            }).toDict()
        return doToken(ParserTokenType.INSTANTIATION, {
            'type_ref': {
                'name': PowangArray.type,
                'type_parameters': [self._auto_type_node()],
            },
            'arguments': [{'name': None, 'value': element} for element in elements],
            'named': False,
            'line': None,
            'column': None,
        }).toDict()

    def helper_getMultipleStatements(self, where: str, condition_token: LexerTokenType):
        statements: list[DictRepr] = []
        while self.next.type != condition_token:
            stmt = self.ExpressionStatement()
            require(stmt is not None, lambda: powang_error_syntax(where, "Reached end of file"))
            statements.append(stmt)
        self.consume(condition_token)
        return statements

    def BlockStatement(self):
        self.consume(LexerTokenType.LEFT_BRACE)
        statements = self.helper_getMultipleStatements('block expression', LexerTokenType.RIGHT_BRACE)
        return doToken(ParserTokenType.BLOCK_STATEMENT, statements).toDict()

    def Type(self, pipe_can_start_member: bool = False):
        """Parse a type annotation, including union alternatives.

        ``pipe_can_start_member`` is enabled only for a member type inside a
        type body, where a following ``|`` may start the next member instead of
        another union branch.
        """
        return self._TypeUnion(pipe_can_start_member)

    def _TypeUnion(self, pipe_can_start_member: bool = False) -> DictRepr:
        branches: list[DictRepr] = [self._TypePrimary(pipe_can_start_member)]
        while self.next is not None and self.next.type == LexerTokenType.PIPE:
            if pipe_can_start_member and self._pipe_starts_member():
                break
            self.advance('union type')
            branches.append(self._TypePrimary(pipe_can_start_member))
        if len(branches) == 1:
            return branches[0]
        first_inner = copy.deepcopy(branches[0]['value'])
        first_inner['alternatives'] = branches
        return doToken(ParserTokenType.TYPE, first_inner).toDict()

    def _TypePrimary(self, pipe_can_start_member: bool = False) -> DictRepr:
        reference = False
        weak = False
        if self.next.type == LexerTokenType.AMPERSAND:
            self.advance('type reference')
            reference = True
        if self.next.type == LexerTokenType.ARROBA:
            self.advance('weak type')
            weak = True

        if self.next.type == LexerTokenType.LEFT_PARENTHESIS:
            self.advance('parenthesized type')
            node = self.Type()
            self.consume(LexerTokenType.RIGHT_PARENTHESIS, 'parenthesized type')
        else:
            start_token = self.next
            type_identifier: str = self.Identifier()['value']
            original_identifier = type_identifier
            generics: list = []
            variadic: bool = False
            element_type: Optional[DictRepr] = None

            if type_identifier in ('tup', PowangMap.type) and self.next.type == LexerTokenType.LEFT_BRACKET:
                self.consume(LexerTokenType.LEFT_BRACKET)
                while self.next.type != LexerTokenType.RIGHT_BRACKET:
                    if self.next.type == LexerTokenType.ELLIPSIS:
                        self.advance('variadic type')
                        variadic = True
                        break
                    generics.append(self.Type())
                    if self.next.type == LexerTokenType.COMMA:
                        self.advance()
                    elif self.next.type != LexerTokenType.RIGHT_BRACKET:
                        raise powang_throw(powang_error_syntax('generic type', "Expected ',' or ']' in type[...]", [
                            f"but {TokenToString(self.next.type)} was encountered",
                        ]))
                self.consume(LexerTokenType.RIGHT_BRACKET)
            elif type_identifier != PowangArray.type and self.next.type == LexerTokenType.LEFT_BRACKET:
                self.consume(LexerTokenType.LEFT_BRACKET, 'type arguments')
                while self.next.type != LexerTokenType.RIGHT_BRACKET:
                    generics.append(self.Type())
                    if self.next.type == LexerTokenType.COMMA:
                        self.advance()
                    elif self.next.type != LexerTokenType.RIGHT_BRACKET:
                        raise powang_throw(self._syntax_at_current(powang_error_syntax(
                            'type arguments', "Expected ',' or ']' in type arguments",
                        )))
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

            if weak: require(type_identifier != PowangNova.type, lambda: powang_error_format(
                "LOGIC", 'type notation', "A nova type can't be weak", [
                    "this has no sense"
            ]))

            const = False
            error_union = False
            if self.next.type == LexerTokenType.EXCLAMATION:
                self.advance('type postfix')
                const = True
            if self.next.type == LexerTokenType.EXCLAMATION:
                self.advance('type inner postfix')
                if original_identifier == PowangArray.type and isinstance(element_type, dict):
                    element_type['value']['const'] = True
                elif original_identifier == PowangMap.type and len(generics) >= 2:
                    generics[1]['value']['const'] = True
                elif original_identifier == PowangSet.type and generics:
                    generics[0]['value']['const'] = True

            if original_identifier == 'tup':
                if const:
                    raise powang_throw(self._syntax_at_current(powang_error_syntax(
                        'tuple type', "tuple types are immutable by default",
                        ["remove the '!' qualifier from tup[...]"],
                    )))
                for generic in generics:
                    inner = generic.get('value') if isinstance(generic, dict) else None
                    if isinstance(inner, dict) and inner.get('const') and \
                            inner.get('value') not in {PowangArray.type, PowangMap.type, PowangSet.type, PowangTuple.type}:
                        raise powang_throw(self._syntax_at_current(powang_error_syntax(
                            'tuple type', "tuple elements are immutable by default",
                            ["remove the '!' qualifier from the element type"],
                        )))
            if original_identifier == PowangMap.type and generics:
                key_inner = generics[0].get('value') if isinstance(generics[0], dict) else None
                if isinstance(key_inner, dict) and key_inner.get('const'):
                    raise powang_throw(self._syntax_at_current(powang_error_syntax(
                        'map type', "map keys are immutable by default",
                        ["did you mean map[str, int]! ?"],
                    )))

            if reference and const:
                raise powang_throw(powang_error_format(
                    "LOGIC", 'type notation', "A reference can't be constant", [
                        "references point at an existing variable"
                    ]))

            if type_identifier in self.type_alias:
                alias = self.type_alias[type_identifier]
                if isinstance(alias, dict) and alias.get('alternatives'):
                    aliased_node = doToken(
                        ParserTokenType.TYPE, copy.deepcopy(alias)
                    ).toDict()
                    aliased_inner = aliased_node.get('value')
                    if isinstance(aliased_inner, dict):
                        if weak:
                            aliased_inner['weak'] = True
                        if const:
                            aliased_inner['const'] = True
                        if error_union:
                            aliased_inner['error_union'] = True
                        if reference:
                            aliased_inner['reference'] = True
                    return aliased_node
                if weak: require(not alias['weak'], lambda: powang_error_format('LOGIC', 'type notation', 'Weak notation in a weak type alias', [
                    f"type alias {type_identifier} already refers to a weak {alias['value']}"
                ]))
                weak = alias['weak']
                if const: require(not alias['const'], lambda: powang_error_format('LOGIC', 'type notation', 'Constant notation in a constant type lias', [
                    f"type alias {type_identifier} already refers to a constant {alias['value']}"
                ]))
                const = alias['const']
                if element_type is None and alias.get('element_type') is not None:
                    element_type = alias['element_type']
                type_identifier = alias['value']

            ## `any` is the gradual unknown used by bare `arr` sugar.
            if type_identifier == 'any':
                type_identifier = PowangAnyType.type

            ## A trailing `?` marks an error-union return annotation:
            ## `fun find(id: int): map? { ... }` may also return `error`.
            if self.next.type == LexerTokenType.QUESTION_MARK:
                self.advance('type error union')
                error_union = True

            node = doToken(ParserTokenType.TYPE, {
                "value": type_identifier,
                "weak": weak,
                "const": const,
                "error_union": error_union,
                "reference": reference,
                "element_type": element_type,
                "generics": generics,
                "variadic": variadic,
                "alternatives": [],
                "auto": type_identifier == 'auto',
                "line": start_token.line if start_token is not None else None,
                "column": start_token.column if start_token is not None else None,
            }).toDict()

        inner = node.get('value')
        if isinstance(inner, dict):
            if reference:
                inner['reference'] = True
            if weak:
                inner['weak'] = True
            if self.next is not None and self.next.type == LexerTokenType.EXCLAMATION:
                self.advance('type postfix')
                inner['const'] = True
            if self.next is not None and self.next.type == LexerTokenType.QUESTION_MARK:
                self.advance('type error union')
                inner['error_union'] = True
        return node

    def _pipe_starts_member(self) -> bool:
        """Look ahead past ``|`` to decide between a union and a new member."""
        state = self._saveParserState()
        try:
            self.advance('member lookahead')
            if self.next.type in {
                LexerTokenType.PIPE,
                LexerTokenType.OPERATOR_PLUS,
                LexerTokenType.OPERATOR_MINUS,
            }:
                return True
            if self.next.type == LexerTokenType.IDENTIFIER:
                self.advance('member lookahead')
                return self.next.type == LexerTokenType.COLON
            return False
        finally:
            self._restoreParserState(state)


    def helper_KeyValuePair(self, key: DictRepr):
        self.consume(LexerTokenType.RIGHT_ARROW)
        value = self.Expression()
        return doToken(ParserTokenType.KEY_VALUE_PAIR, {
            "key": key,
            "value": value,
        }).toDict()

    def Literal(self, where: Optional[str] = None):
        require(self.next is not None, lambda: powang_error_syntax_unexpected_end(where, self.tokenizer))
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
        raise powang_throw(self._syntax_at_current(powang_error_syntax_unexpected_token(
            where,
            LexerTokenType.toStr(self.next.type),
            'literal',
        )))

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

    def _syntax_at_current(self, error: PowangError) -> PowangError:
        token = self.next
        if token is None:
            return error
        return powang_error_with_position(
            error,
            (token.line + 1) if getattr(token, 'line', None) is not None else None,
            getattr(token, 'column', None),
        )

    def advance(self, where: Optional[str] = None):
        return self.consume(self.next.type, where)

    def consume(self, token_type: LexerTokenType, where: Optional[str] = None):
        token = self.next
        require(token is not None, lambda: powang_error_syntax_unexpected_end(None, self.tokenizer))

        if token.type != token_type:
            raise powang_throw(powang_error_with_position(
                powang_error_syntax_unexpected_token(
                    where,
                    f"{LexerTokenType.toStr(token.type)}",
                    f"{LexerTokenType.toStr(token_type)}",
                ),
                (token.line + 1) if token.line is not None else None,
                token.column,
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
            'element_type': None,
            'generics': [],
            'variadic': False,
            'alternatives': [],
            'auto': False,
        }).toDict()