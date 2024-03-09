from dataclasses import dataclass
from pathlib import Path

from .config import HookConfig


@dataclass(frozen=True, slots=True, kw_only=True)
class ExecutableUnit:
    id: int
    hook: HookConfig
    targets: frozenset[Path] = frozenset()
