import sys
import shutil
from pathlib import Path
from typing import final, Final, Container, Sequence

from .backend.index import load_backend
from .config import EnvironmentConfig


def probe_orphans(
    environments: Container[str],
    env_dir: Path,
    delete: bool,
) -> None:
    for path in env_dir.glob("*"):
        if not path.is_dir():
            continue
        if path.name in environments:
            continue
        if delete:
            print(f"Deleting orphan environment {path.name!r}", file=sys.stderr)
            shutil.rmtree(path)
        else:
            print(f"Warning: orphan environment {path.name!r}", file=sys.stderr)


@final
class Environment:
    def __init__(
        self,
        config: EnvironmentConfig,
        environments_path: Path,
        lock_files_path: Path,
    ) -> None:
        self._config: Final = config
        self._backend: Final = load_backend(config.language)
        self._path: Final = environments_path / config.id
        self._lock_files_path: Final = lock_files_path / config.id

    async def bootstrap(self) -> None:
        await self._backend.bootstrap(
            env_path=self._path,
            config=self._config,
        )

    async def freeze(self) -> None:
        await self._backend.freeze(
            env_path=self._path,
            config=self._config,
            lock_files_path=self._lock_files_path,
        )

    async def sync(self) -> None:
        await self._backend.sync(
            env_path=self._path,
            config=self._config,
            lock_files_path=self._lock_files_path,
        )

    async def run(self, command: Sequence[str]) -> None:
        await self._backend.run(
            env_path=self._path,
            config=self._config,
            command=command,
        )
