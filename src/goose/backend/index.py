from . import python
from . import node
from .base import Backend
from typing import Final, Mapping
from types import MappingProxyType

from goose.config import EcosystemConfig

backends: Final[Mapping[str, Backend]] = MappingProxyType(
    {
        "node": node.backend,
        "python": python.backend,
    }
)


def load_backend(ecosystem: EcosystemConfig) -> Backend:
    return backends[ecosystem.language]
