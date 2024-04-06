import enum
from collections.abc import Awaitable
from collections.abc import Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from typing import final

from goose.config import EnvironmentConfig
from goose.executable_unit import ExecutableUnit


class Bootstrap(Protocol):
    def __call__(
        self,
        *,
        config: EnvironmentConfig,
        env_path: Path,
    ) -> Awaitable[None]: ...


class Freeze(Protocol):
    def __call__(
        self,
        *,
        config: EnvironmentConfig,
        env_path: Path,
        lock_files_path: Path,
    ) -> Awaitable[None]: ...


class Sync(Protocol):
    def __call__(
        self,
        *,
        config: EnvironmentConfig,
        env_path: Path,
        lock_files_path: Path,
    ) -> Awaitable[None]: ...


class RunResult(enum.Enum):
    ok = enum.auto()
    error = enum.auto()
    modified = enum.auto()


class Run(Protocol):
    def __call__(
        self,
        *,
        config: EnvironmentConfig,
        env_path: Path,
        unit: ExecutableUnit,
    ) -> Coroutine[None, None, RunResult]: ...


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class Backend:
    ecosystem: str
    bootstrap: Bootstrap
    """
    - Create environment if it does not exist.
    - Install basic dependencies to enable freezing.
    """
    freeze: Freeze
    """
    - Update lock file.
    """
    sync: Sync
    """
    - Install missing dependencies.
    - Uninstall obsolete dependencies.
    """
    run: Run
