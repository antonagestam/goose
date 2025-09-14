import asyncio
import os
import platform
from pathlib import Path
from typing import IO
from typing import Final

from goose.backend.base import Backend
from goose.backend.base import InitialStage
from goose.backend.base import InitialState
from goose.backend.base import RunResult
from goose.backend.base import SyncedStage
from goose.backend.base import SyncedState
from goose.config import EnvironmentConfig
from goose.executable_unit import ExecutableUnit
from goose.manifest import LockManifest
from goose.manifest import build_manifest
from goose.process import stream_both


async def bootstrap(
    env_path: Path,
    config: EnvironmentConfig,
    manifest: LockManifest | None,
) -> InitialState:
    env_path.mkdir(exist_ok=True)
    return InitialState(
        stage=InitialStage.bootstrapped,
        ecosystem=config.ecosystem,
        bootstrapped_version=f"{platform.system()}-{platform.release()}",
    )


async def freeze(
    env_path: Path,
    config: EnvironmentConfig,
    lock_files_path: Path,
) -> tuple[InitialState, LockManifest]:
    state = InitialState(
        stage=InitialStage.frozen,
        ecosystem=config.ecosystem,
        bootstrapped_version=f"{platform.system()}-{platform.release()}",
    )
    manifest = build_manifest(
        source_ecosystem=config.ecosystem,
        source_dependencies=config.dependencies,
        lock_files=(),
        lock_files_path=lock_files_path,
        ecosystem_version=state.bootstrapped_version,
    )
    return state, manifest


async def sync(
    env_path: Path,
    config: EnvironmentConfig,
    lock_files_path: Path,
    manifest: LockManifest,
) -> SyncedState:
    return SyncedState(
        stage=SyncedStage.synced,
        checksum=manifest.checksum,
        ecosystem=config.ecosystem,
        bootstrapped_version=f"{platform.system()}-{platform.release()}",
    )


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
