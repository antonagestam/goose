import asyncio
import asyncio.subprocess
import contextlib
import os
import re
import shutil
import sys
from collections.abc import Iterator
from collections.abc import Mapping
from collections.abc import Sequence
from io import StringIO
from pathlib import Path
from typing import IO
from typing import Final

from pydantic import Field

from goose._utils.pydantic import BaseModel
from goose.config import EnvironmentConfig
from goose.config import get_ecosystem_version
from goose.executable_unit import ExecutableUnit
from goose.manifest import LockManifest
from goose.manifest import build_manifest
from goose.process import stream_both
from goose.process import stream_out
from goose.process import system_python

from .base import Backend
from .base import InitialStage
from .base import InitialState
from .base import RunResult
from .base import SyncedStage
from .base import SyncedState


class PackageJson(BaseModel):
    lockfile_version: int = Field(default=3, serialization_alias="lockfileVersion")
    dependencies: Mapping[str, str]


def _bootstrap_env() -> dict[str, str]:
    return os.environ | {
        "PYTHONUNBUFFERED": "1",
    }


def _npm_path_env(env_path: Path) -> dict[str, str]:
    return {"PATH": f"{os.environ['PATH']}:{env_path / 'bin'}"}


def _npm_install_env(env_path: Path) -> dict[str, str]:
    return {
        **_npm_path_env(env_path),
        "NPM_CONFIG_FUND": "false",
    }


async def _create_node_env(env_path: Path, version: str) -> None:
    process = await asyncio.create_subprocess_exec(
        system_python(),
        *(
            "-m",
            "nodeenv",
            f"--node={version}",
            str(env_path),
        ),
        env=_bootstrap_env(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await stream_both(process)
    await process.wait()
    if process.returncode != 0:
        raise RuntimeError(f"Failed creating node env {process.returncode=}")


async def _spawn_version_process(env_path: Path) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        "node",
        "--version",
        env=_npm_path_env(env_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


async def _gather_version_process(
    process: asyncio.subprocess.Process,
    configured_version: str | None,
) -> str:
    version_buffer = StringIO()
    assert process.stdout is not None
    assert process.stderr is not None
    stream_stderr = stream_out(f"{process}[stderr]", process.stderr, sys.stderr)
    capture_stdout = stream_out("", process.stdout, version_buffer)
    await asyncio.gather(stream_stderr, capture_stdout)
    await process.wait()
    if process.returncode != 0:
        raise RuntimeError(
            f"Failed getting version from node env {process.returncode=}"
        )
    ecosystem_version = version_buffer.getvalue().strip().removeprefix("v")
    if configured_version is not None and not ecosystem_version.startswith(
        configured_version
    ):
        raise RuntimeError(
            f"Resulting version of venv ({ecosystem_version}) does not match "
            f"environment config ({configured_version})"
        )
    return ecosystem_version


_versions_delimiter: Final = re.compile(r"[\t\n]")


def _string_version_as_sortable(string_version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in string_version.split("."))


def _sortable_version_as_string(sortable_version: tuple[int, ...]) -> str:
    return ".".join(str(part) for part in sortable_version)


async def _get_highest_matching_version(configured_version: str | None) -> str:
    process = await asyncio.create_subprocess_exec(
        system_python(),
        "-m",
        "nodeenv",
        "--list",
        env=_bootstrap_env(),
        stderr=asyncio.subprocess.PIPE,
    )
    output_buffer = StringIO()
    assert process.stderr is not None
    await stream_out("", process.stderr, output_buffer)
    await process.wait()
    if process.returncode != 0:
        raise RuntimeError(
            f"Failed listing available node versions {process.returncode=}"
        )
    available_versions = (
        _string_version_as_sortable(version_string)
        for unclean_string in _versions_delimiter.split(
            output_buffer.getvalue().strip()
        )
        if (version_string := unclean_string.strip())
        if configured_version is None or version_string.startswith(configured_version)
    )
    try:
        version = max(available_versions)
    except ValueError as exception:
        raise RuntimeError(
            f"Found no available node versions matching {configured_version=}"
        ) from exception
    return _sortable_version_as_string(version)


async def bootstrap(
    env_path: Path,
    config: EnvironmentConfig,
    manifest: LockManifest | None,
) -> InitialState:
    configured_version = get_ecosystem_version(config.ecosystem)

    if manifest is None:
        version = await _get_highest_matching_version(configured_version)
    else:
        version = manifest.ecosystem_version

    print(
        f"Creating node env at {env_path.name} with version {version}",
        file=sys.stderr,
    )
    await _create_node_env(env_path, version)
    process = await _spawn_version_process(env_path)
    bootstrapped_version = await _gather_version_process(
        process,
        configured_version,
    )
    return InitialState(
        stage=InitialStage.bootstrapped,
        ecosystem=config.ecosystem,
        bootstrapped_version=bootstrapped_version,
    )


def _write_package_json(
    config: EnvironmentConfig,
    lock_files_path: Path,
) -> Path:
    package_json_path = lock_files_path / "package.json"
    package_json = PackageJson(
        dependencies={
            # todo: support version specs
            dependency: "*"
            for dependency in config.dependencies
        }
    )
    with package_json_path.open("w") as fd:
        print(package_json.model_dump_json(by_alias=True), file=fd)
    return package_json_path


@contextlib.contextmanager
def cd_to(path: Path) -> Iterator[None]:
    cd = os.getcwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(cd)


async def freeze(
    env_path: Path,
    config: EnvironmentConfig,
    lock_files_path: Path,
) -> tuple[InitialState, LockManifest]:
    package_json_path = _write_package_json(config, lock_files_path)

    version_process = await _spawn_version_process(env_path)

    with cd_to(lock_files_path):
        process = await asyncio.create_subprocess_exec(
            env_path / "bin" / "npm",
            *(
                "install",
                "--package-lock-only",
            ),
            env=_npm_install_env(env_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await stream_both(process)
        await process.wait()

    if process.returncode != 0:
        raise RuntimeError(f"Failed freezing dependencies {process.returncode=}")

    bootstrapped_version = await _gather_version_process(
        version_process,
        get_ecosystem_version(config.ecosystem),
    )
    state = InitialState(
        stage=InitialStage.frozen,
        ecosystem=config.ecosystem,
        bootstrapped_version=bootstrapped_version,
    )
    package_lock_json_path = lock_files_path / "package-lock.json"
    manifest = build_manifest(
        source_ecosystem=config.ecosystem,
        source_dependencies=config.dependencies,
        lock_files=(
            package_json_path,
            package_lock_json_path,
        ),
        lock_files_path=lock_files_path,
        ecosystem_version=bootstrapped_version,
    )
    return state, manifest


async def sync(
    env_path: Path,
    config: EnvironmentConfig,
    lock_files_path: Path,
    manifest: LockManifest,
) -> SyncedState:
    version_process = await _spawn_version_process(env_path)
    package_lock_path = lock_files_path / "package-lock.json"
    package_json_path = lock_files_path / "package.json"

    shutil.copy(package_lock_path, env_path / package_lock_path.name)
    shutil.copy(package_json_path, env_path / package_json_path.name)

    with cd_to(env_path):
        process = await asyncio.create_subprocess_exec(
            env_path / "bin" / "npm",
            *(
                "install",
                "--no-save",
            ),
            env=_npm_install_env(env_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await stream_both(process)
        await process.wait()

    if process.returncode != 0:
        raise RuntimeError("Failed syncing dependencies {process.returncode=}")

    bootstrapped_version = await _gather_version_process(
        version_process,
        get_ecosystem_version(config.ecosystem),
    )
    return SyncedState(
        stage=SyncedStage.synced,
        checksum=manifest.checksum,
        ecosystem=config.ecosystem,
        bootstrapped_version=bootstrapped_version,
    )


async def run(
    env_path: Path,
    config: EnvironmentConfig,
    unit: ExecutableUnit,
    buffer: IO[str],
) -> RunResult:
    args: Sequence[str | Path] = (
        "exec",
        f"--prefix={env_path}",
        unit.hook.command,
        "--",
        *unit.hook.args,
        *unit.targets,
    )
    process = await asyncio.create_subprocess_exec(
        env_path / "bin" / "npm",
        *args,
        env={
            **os.environ,
            **dict(unit.hook.env_vars),
            **_npm_path_env(env_path),
        },
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await stream_both(process, file=buffer, prefix=unit.log_prefix)
    await process.wait()

    return RunResult.ok if process.returncode == 0 else RunResult.error


backend: Final = Backend(
    ecosystem="node",
    bootstrap=bootstrap,
    freeze=freeze,
    sync=sync,
    run=run,
)
