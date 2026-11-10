# Phase 3D: Character type

Status: complete. Shipped in powang `0.19.0` and powang-lsp `0.25.0`.

## Goal

Add a first-class character type so character-oriented code stops treating
every code point as a one-character string. The type must map cleanly to the
native character types planned for compiled backends.

## Decisions

- `char` is one Unicode scalar value, not a UTF-8 byte.
- Surrogate code points and values above `U+10FFFF` are rejected.
- Character literals use single quotes, for example `'a'`.
- Escapes match strings. The escape set is `\n`, `\t`, `\r`, `\\`, `\'`, `\"`,
  `\0` and `\u{HEX}`. Unicode escapes also work inside strings.
- Character ordering and hashing use the code point.
- Two characters concatenate into a `str`. A character also concatenates with
  a `str` on either side.
- Explicit casts convert between `char` and one-character `str`. A string
  annotation does not require a cast when the source is a `char` because that
  conversion cannot fail.

## String access during migration

String indexing and string iteration keep returning a one-character `str`.
That preserves existing code and all existing examples.

New code should use explicit character access:

- `str.char_at(index)` returns a `char` and supports negative indexes.
- `str.chars()` returns `arr[char]`.
- `str.get(index)` remains the string-returning index helper.
- Iterating a `str` still yields one-character strings.

The compiled backend can store strings as UTF-32 or maintain a code point
index so `char_at` is O(1). The interpreter uses Python's code point strings,
so `char_at` is O(1) for the current representation.

## Builtins

Every predicate accepts a `char` or a one-character `str`:

- `is_digit`, `is_alpha`, `is_alnum`, `is_space`, `is_upper`, `is_lower` and
  `is_ascii` return `bool`.
- `ord` returns an `int`.
- `chr` returns a `char`.
- `digit_value` returns `0` to `9`, or `-1` for a non-digit.

The predicates are ASCII based. Unicode case or digit classification can be a
separate opt-in feature.

## Native methods

`char` has the native methods `code`, `to_str`, `is_digit`, `is_alpha`,
`is_alnum`, `is_space`, `is_upper`, `is_lower` and `is_ascii`.

`str.add`, `str.sub`, `str.count` and `str.div` accept a `char` or a `str`
operand. `str.char_at` and `str.chars` are the character access methods.

## Tooling

- The LSP recognizes character literals in the grammar and semantic tokens.
- Completion offers `char` as a builtin type.
- Hover documents `char` and the character builtins.
- Completion and hover cover character native methods and `str.char_at` and
  `str.chars`.
- The LSP tracks single-quoted literals when it parses arguments, signatures
  and interpolation expressions.

## Tests

`tests/test_characters.py` covers literals, escapes, casts, construction,
predicates, native methods, typed arrays, match patterns, map and set keys,
interpolation, invalid literals and unsupported arithmetic. The example
`examples/characters.po` is part of the example suite. `examples/calc.po` uses
`char`, `str.char_at`, `is_space` and `is_digit` in its lexer.
