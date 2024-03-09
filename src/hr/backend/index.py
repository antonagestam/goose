
from . import python
from .base import Backend
from typing import Final, Mapping
from types import MappingProxyType

from hr.config import LanguageConfig

_backends: Final[Mapping[str, Backend]] = MappingProxyType({
    "python": python.backend,
})


def load_backend(language: LanguageConfig) -> Backend:
    return _backends[language.id]
