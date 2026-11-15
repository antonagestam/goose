from __future__ import annotations

from dataclasses import dataclass
from itertools import zip_longest
from typing import assert_never


@dataclass(frozen=True, slots=True)
class AlphaIdentifier:
    value: str

    def __lt__(self, other: Identifier) -> bool:
        match other:
            case NumericIdentifier():
                return False
            case AlphaIdentifier(value=other_value):
                return self.value < other_value
            case no_match:
                assert_never(no_match)


@dataclass(frozen=True, slots=True)
class NumericIdentifier:
    value: int

    def __lt__(self, other: Identifier) -> bool:
        match other:
            case NumericIdentifier(value=other_value):
                return self.value < other_value
            case AlphaIdentifier():
                return True
            case no_match:
                assert_never(no_match)


type Identifier = AlphaIdentifier | NumericIdentifier


@dataclass(frozen=True, slots=True)
class Version:
    major: int
    minor: int
    patch: int
    suffix: tuple[Identifier, ...]

    def __lt__(self, other: Version) -> bool:  # noqa: C901
        if self.major != other.major:
            return self.major < other.major
        if self.minor != other.minor:
            return self.minor < other.minor
        if self.patch != other.patch:
            return self.patch < other.patch

        if not self.suffix and other.suffix:
            return False
        if self.suffix and not other.suffix:
            return True

        for self_identifier, other_identifier in zip_longest(
            self.suffix,
            other.suffix,
            fillvalue=None,
        ):
            if self_identifier is None:
                return True
            if other_identifier is None:
                return False
            if self_identifier < other_identifier:
                return True
            if self_identifier > other_identifier:
                return False

        return False

    def format(self) -> str:
        if self.suffix:
            suffix = "-" + ".".join(
                [str(identifier.value) for identifier in self.suffix]
            )
        else:
            suffix = ""
        return f"{self.major}.{self.minor}.{self.patch}{suffix}"


def _parse_suffix_identifier(token: str) -> Identifier:
    try:
        return NumericIdentifier(int(token))
    except ValueError:
        return AlphaIdentifier(token)


def parse_suffix(subject: str) -> tuple[str, tuple[Identifier, ...]]:
    match subject.split("-", maxsplit=2):
        case (main_version, suffix):
            return (
                main_version,
                tuple(_parse_suffix_identifier(token) for token in suffix.split(".")),
            )
        case (main_version,):
            return main_version, ()
        case _:
            raise NotImplementedError


def parse_version(version_str: str) -> Version:
    main_subject, suffix = parse_suffix(version_str)

    match tuple(int(part) for part in main_subject.split(".", maxsplit=4)):
        case (major, minor, patch):
            return Version(major, minor, patch, suffix)

    raise ValueError(f"Invalid version string: {version_str}")
