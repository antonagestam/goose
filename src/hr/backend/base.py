import enum
from pathlib import Path

from hr.config import EnvironmentConfig
from dataclasses import dataclass
from typing import final, Awaitable, Protocol, Coroutine

from hr.executable_unit import ExecutableUnit


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
