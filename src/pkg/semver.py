"""Semantic version parsing and dependency constraints for packages."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from ..error import powang_error_format, powang_throw


_VERSION_RE = re.compile(r'^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?$')
_TERM_RE = re.compile(r'(>=|<=|>|<|=|\^|~)?\s*(\d+(?:\.\d+){0,2})')


@dataclass(frozen=True, order=False)
class Version:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, text: str) -> 'Version':
        if not isinstance(text, str):
            raise powang_throw(powang_error_format(
                'PACKAGE',
                'version',
                'package versions must be strings',
                [f"but {type(text).__name__} was encountered"],
            ))
        match = _VERSION_RE.match(text.strip())
        if match is None:
            raise powang_throw(powang_error_format(
                'PACKAGE',
                'version',
                f"invalid package version '{text}'",
                ['write versions as major.minor.patch, for example 1.2.0'],
            ))
        major = int(match.group(1))
        minor = int(match.group(2) or 0)
        patch = int(match.group(3) or 0)
        return cls(major, minor, patch)

    def bump_major(self) -> 'Version':
        return Version(self.major + 1, 0, 0)

    def bump_minor(self) -> 'Version':
        return Version(self.major, self.minor + 1, 0)

    def bump_patch(self) -> 'Version':
        return Version(self.major, self.minor, self.patch + 1)

    def __str__(self) -> str:
        return f'{self.major}.{self.minor}.{self.patch}'

    def __repr__(self) -> str:
        return f'Version({self.major}, {self.minor}, {self.patch})'

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return (self.major, self.minor, self.patch) < (
            other.major, other.minor, other.patch
        )

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self == other or self < other

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return not self <= other

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return not self < other

    def __hash__(self) -> int:
        return hash((self.major, self.minor, self.patch))


@dataclass(frozen=True)
class Comparator:
    operator: str
    version: Version

    def matches(self, version: Version) -> bool:
        if self.operator == '=':
            return version == self.version
        if self.operator == '>':
            return version > self.version
        if self.operator == '>=':
            return version >= self.version
        if self.operator == '<':
            return version < self.version
        if self.operator == '<=':
            return version <= self.version
        return False

    def __str__(self) -> str:
        return f'{self.operator}{self.version}'


class Constraint:
    """A conjunction of version comparators."""

    def __init__(self, text: str, comparators: Iterable[Comparator]):
        self.text = text.strip()
        self.comparators = tuple(comparators)

    @classmethod
    def any(cls) -> 'Constraint':
        return cls('*', ())

    @classmethod
    def exact(cls, version: Version) -> 'Constraint':
        return cls(str(version), (Comparator('=', version),))

    @classmethod
    def parse(cls, text: str) -> 'Constraint':
        if not isinstance(text, str):
            raise powang_throw(powang_error_format(
                'PACKAGE',
                'dependency',
                'version constraints must be strings',
                [f"but {type(text).__name__} was encountered"],
            ))
        raw = text.strip()
        if raw in ('', '*'):
            return cls.any()

        comparators: list[Comparator] = []
        position = 0
        for match in _TERM_RE.finditer(raw):
            gap = raw[position:match.start()]
            if gap.strip(' \t,'):
                raise cls._invalid(text)
            operator = match.group(1)
            version_text = match.group(2)
            parts = version_text.split('.')
            version = Version.parse(version_text)
            if operator == '^':
                comparators.extend(cls._caret(version))
            elif operator == '~':
                comparators.extend(cls._tilde(version, len(parts)))
            elif operator is None:
                comparators.append(Comparator('=', version))
            else:
                comparators.append(Comparator(operator, version))
            position = match.end()
        if not comparators or raw[position:].strip(' \t,'):
            raise cls._invalid(text)
        return cls(raw, comparators)

    @classmethod
    def _caret(cls, version: Version) -> list[Comparator]:
        lower = Comparator('>=', version)
        if version.major > 0:
            upper = Comparator('<', version.bump_major())
        elif version.minor > 0:
            upper = Comparator('<', version.bump_minor())
        else:
            upper = Comparator('<', version.bump_patch())
        return [lower, upper]

    @classmethod
    def _tilde(cls, version: Version, specified_parts: int) -> list[Comparator]:
        lower = Comparator('>=', version)
        if specified_parts <= 1:
            upper = Comparator('<', version.bump_major())
        else:
            upper = Comparator('<', version.bump_minor())
        return [lower, upper]

    @staticmethod
    def _invalid(text: str):
        return powang_error_format(
            'PACKAGE',
            'dependency',
            f"invalid version constraint '{text}'",
            [
                "use an exact version, a caret range, a tilde range or comparison operators",
                "examples: 1.2.0, ^1.2.0, ~1.2.0, >=1.0.0 <2.0.0",
            ],
        )

    def matches(self, version: Version) -> bool:
        return all(comparator.matches(version) for comparator in self.comparators)

    def is_any(self) -> bool:
        return not self.comparators

    def __str__(self) -> str:
        return self.text or '*'

    def __repr__(self) -> str:
        return f'Constraint({self.text!r})'


def select_versions(
    versions: Iterable[Version],
    constraints: Iterable[Constraint],
) -> list[Version]:
    constraint_list = list(constraints)
    selected = [
        version for version in versions
        if all(constraint.matches(version) for constraint in constraint_list)
    ]
    return sorted(selected, reverse=True)
