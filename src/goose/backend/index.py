from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from . import node
from . import python
from . import system
from .base import Backend

backends: Final[Mapping[str, Backend]] = MappingProxyType(
    {
        "node": node.backend,
        "python": python.backend,
        "system": system.backend,
    }
)


def load_backend(language: str) -> Backend:
    return backends[language]
