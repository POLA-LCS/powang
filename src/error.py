from typing import Optional


def _format_error_text(
    name: Optional[str] = None,
    where: Optional[str] = None,
    resume: Optional[str] = None,
    messages: Optional[list[str]] = None,
) -> str:
    """Render the stable `[KIND ERROR]` text used by every diagnostic."""
    if messages is None:
        messages = []
    error_message: str = '[ERROR]' if not name else f'[{name} ERROR]'
    if where:
        error_message += f' (in {where})'
    if resume:
        error_message += ' ' + resume
    if messages:
        error_message += ':'
        for msg in messages:
            error_message += '\n      | ' + msg
    return error_message


class PowangError(AssertionError):
    """A catchable language error.

    Subclasses ``AssertionError`` on purpose so that the CLI, the REPL and any
    existing ``except AssertionError`` handler keep working unchanged, while
    Powang code can still catch it through ``try``/``catch``.

    ``str(error)`` is byte-for-byte the same text the diagnostic helpers used
    to return before this class existed.
    """

    def __init__(
        self,
        kind: Optional[str] = None,
        message: str = '',
        details: Optional[list[str]] = None,
        where: Optional[str] = None,
        line: Optional[int] = None,
        column: Optional[int] = None,
        frames: Optional[list[str]] = None,
        cause: Optional['PowangError'] = None,
        text: Optional[str] = None,
    ):
        self.kind: str = kind if kind else 'ERROR'
        self.message: str = message
        self.details: list[str] = list(details) if details else []
        self.where: Optional[str] = where
        self.line: Optional[int] = line
        self.column: Optional[int] = column
        self.frames: list[str] = list(frames) if frames else []
        self.cause: Optional['PowangError'] = cause
        self.text: str = text if text is not None else _format_error_text(
            None if self.kind == 'ERROR' else self.kind,
            self.where,
            self.message,
            self.details,
        )
        AssertionError.__init__(self, self.text)

    def __str__(self) -> str:
        return self.text

    def __repr__(self) -> str:
        return f'PowangError({self.kind!r}, {self.message!r})'

    def with_line(self, line: Optional[int]) -> 'PowangError':
        """Return a copy carrying a source line, keeping the rendered text stable."""
        if line is None:
            return self
        copy = PowangError(
            self.kind,
            self.message,
            self.details,
            self.where,
            line,
            self.column,
            self.frames,
            self.cause,
            text=f"ln: {line} | {str(self)}",
        )
        end_column = getattr(self, 'end_column', None)
        if end_column is not None:
            copy.end_column = end_column
        return copy


def powang_error_from_exception(exc: BaseException) -> Optional[PowangError]:
    """Extract a ``PowangError`` from an exception, if it carries one.

    Language checks still use ``assert condition, powang_error_...(...)`` in
    many places. Such an assert raises a plain ``AssertionError`` whose first
    argument is a ``PowangError``. This helper normalizes that shape without
    treating unrelated Python assertion failures as catchable language errors.
    """
    if isinstance(exc, PowangError):
        return exc
    if isinstance(exc, AssertionError) and exc.args:
        candidate = exc.args[0]
        if isinstance(candidate, PowangError):
            return candidate
    return None


def powang_throw(error) -> None:
    """Raise a ``PowangError``.

    Accepts either an already built ``PowangError``, an ``AssertionError``
    that wraps one, or a plain string (kept for backwards compatibility).
    """
    if isinstance(error, PowangError):
        raise error
    converted = powang_error_from_exception(error)
    if converted is not None:
        raise converted
    text = str(error)
    raise PowangError(None, text, text=text)


def powang_error_format(
    name: Optional[str] = None,
    where: Optional[str] = None,
    resume: Optional[str] = None,
    messages: Optional[list[str]] = None,
) -> PowangError:
    if messages is None:
        messages = []
    return PowangError(
        name if name else 'ERROR',
        resume if resume else '',
        list(messages),
        where,
    )


def powang_error_syntax(
    where: Optional[str],
    resume: Optional[str],
    messages: Optional[list[str]] = None,
) -> PowangError:
    if messages is None:
        messages = []
    return powang_error_format('SYNTAX', where, resume, messages)


def powang_error_with_position(
    error: PowangError,
    line: Optional[int],
    column: Optional[int],
    end_column: Optional[int] = None,
) -> PowangError:
    """Attach a precise source position to an existing diagnostic."""
    if line is not None:
        error.line = line
    if column is not None:
        error.column = column
    if end_column is not None:
        error.end_column = end_column
    return error


def powang_error_syntax_unexpected_end(
    where: Optional[str],
    tokenizer: object
):  return powang_error_syntax(where, "Unexpected end of input", [
    tokenizer.data[tokenizer.row] # type: ignore
])


def powang_error_syntax_unexpected_token(
    where: Optional[str],
    encountered: str,
    expected: str,
):  return powang_error_syntax(where, f"Unexpected token", [
    f"expected {expected}",
    f"but {encountered} was encountered"
])


def powang_error_identifier_not_found(
    where     : Optional[str],
    identifier: str,
    messages  : Optional[list[str]] = None,
) -> PowangError:
    if messages is None:
        messages = []
    return powang_error_format('IDENTIFIER', where, "doens't exists", [
        identifier,
    ] + messages)

def powang_error_identifier_type(
    where     : Optional[str],
    type_id   : str,
    messages  : Optional[list[str]] = None,
) -> PowangError:
    if messages is None:
        messages = []
    return powang_error_format('TYPE', where, "Identifier does not name a valid type", [
        type_id
    ] + messages)

def powang_error_type_match(
    where     : Optional[str],
    expected  : str,
    encounter : str,
) -> PowangError:  return powang_error_format('TYPE', where, "Types doesn't match", [
    f"expected {expected}",
    f"but {encounter} was encounter"
])

def powang_error_strong_nova_assign(
    where : Optional[str],
    type : str,
) -> PowangError:  return powang_error_format('ASSIGN', where, "Weak assign to strong value", [
    f"trying to assign nova to a strong {type}"
])

def powang_error_undefined_reference(
    where      : Optional[str],
    undefined  : str,
) -> PowangError:  return powang_error_format('REFERENCE', where, f"Undefined reference: {undefined}\n",)

def powang_error_undefined_argument(
    where     : Optional[str],
    parameter : int,
    type  : str,
) -> PowangError:  return powang_error_format('CALL', f'function call: {where}',
    'undefined parameter', [
    f"parameter number {parameter}",
    f"is an undefined value of type {type}"
])

def powang_error_invalid_input(
    where     : Optional[str],
    value     : str,
    type      : str,
) -> PowangError:  return powang_error_format('INPUT', where, 'Invalid input for specified type', [
    f"cannot convert {value}",
    f"into type {type}",
])

def powang_error_invalid_type_for_prefix_operator(
    where    : Optional[str],
    operator : str,
    type     : str,
) -> PowangError:  return powang_error_format('PREFIX', where, 'Unsupported prefix', [
    f'for prefix "{operator}"',
    f'and type "{type}"',
])

def powang_error_index_out_of_range(
    index : int,
    size  : int,
) -> PowangError:  return powang_error_format('INDEX', None, 'Out of range', [
    f"index {index} out of range [0; {size})"
])

def powang_error_key(
    key   : str,
) -> PowangError:  return powang_error_format('KEY', None, f"Does not refers to a value: {key}")

def powang_error_invalid_cast(
    where    : Optional[str],
    cast_to  : str,
    to_cast  : str,
    explicit : bool,
) -> PowangError:  return powang_error_format('TYPE', where, f'Invalid {"explicit" if explicit else ''} cast types', [
    f"unable to cast {to_cast} to {cast_to}"
])

def powang_error_constant_assign(
    where : Optional[str],
    type  : str,
    weak  : bool,
) -> PowangError:  return powang_error_format('ASSIGN', where, "constant assign", [
    f"trying to assign into a {f"not changeable weak" if weak else ''} const {type}"
])

def powang_error_unsupported_operation(
    where    : Optional[str],
    left     : str,
    operator : str,
    right    : Optional[str] = None
) -> PowangError:  return powang_error_format('OPERATION', where, "Invalid operation", [
    f"Unsupported \"{operator}\" operation {"between" if right is not None else "for"} {left} {f"and {right}" if right is not None else ""}",
])

def powang_error_redefined(
    where      : Optional[str],
    identifier : str,
    messages   : Optional[list[str]] = None,
) -> PowangError:
    if messages is None:
        messages = []
    return powang_error_format('REDEFINE', where, 'Name already exists in this scope', [
        f"trying to redefine: {identifier}"] + messages
    )

def powang_error_identifier_names_type(
    where      : Optional[str],
    identifier : str,
) -> PowangError:  return powang_error_format('NAME', where, f"Function identifier names a type: {identifier}")

def powang_error_not_iterable(
    where      : Optional[str],
    type       : str,
    messages   : Optional[list[str]] = None,
) -> PowangError:
    if messages is None:
        messages = []
    return powang_error_format('TYPE', where, f"Object of type {type} is not sizeable", messages)

def powang_error_development(
    where      : Optional[str],
    resume     : str,
    messages   : Optional[list[str]] = None,
) -> PowangError:
    if messages is None:
        messages = []
    return powang_error_format('DEVELOPMENT', where, resume, messages)
