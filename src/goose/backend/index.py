from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from goose.config import EcosystemConfig

from . import node
from . import python
from .base import Backend

backends: Final[Mapping[str, Backend]] = MappingProxyType(
    {
        "node": node.backend,
        "python": python.backend,
    }
)


def load_backend(ecosystem: EcosystemConfig) -> Backend:
    return backends[ecosystem.language]
