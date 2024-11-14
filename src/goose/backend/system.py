import asyncio
import os
from pathlib import Path
from typing import IO
from typing import Final

from goose.backend.base import Backend
from goose.backend.base import RunResult
from goose.config import EnvironmentConfig
from goose.executable_unit import ExecutableUnit
from goose.manifest import LockManifest
from goose.manifest import build_manifest
from goose.process import stream_both


async def bootstrap(
    env_path: Path,
    config: EnvironmentConfig,
) -> None:
    env_path.mkdir(exist_ok=True)


async def freeze(
    env_path: Path,
    config: EnvironmentConfig,
    lock_files_path: Path,
) -> LockManifest:
    return build_manifest(
        source_ecosystem=config.ecosystem,
        source_dependencies=config.dependencies,
        lock_files=(),
        lock_files_path=lock_files_path,
    )


async def sync(
    env_path: Path,
    config: EnvironmentConfig,
    lock_files_path: Path,
) -> None:
    pass


async def run(
    env_path: Path,
    config: EnvironmentConfig,
    unit: ExecutableUnit,
    buffer: IO[str],
) -> RunResult:
    process = await asyncio.create_subprocess_exec(
        unit.hook.command,
        *unit.hook.args,
        *unit.targets,
        env={
            **os.environ,
            **dict(unit.hook.env_vars),
        },
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await stream_both(process, file=buffer, prefix=unit.log_prefix)
    await process.wait()

    return RunResult.ok if process.returncode == 0 else RunResult.error


backend: Final = Backend(
    ecosystem="system",
    bootstrap=bootstrap,
    freeze=freeze,
    sync=sync,
    run=run,
)
