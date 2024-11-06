import asyncio
import asyncio.subprocess
import contextlib
import os
import shutil
import sys
from collections.abc import Iterator
from collections.abc import Mapping
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from pydantic import Field

from goose._utils.pydantic import BaseModel
from goose.config import EnvironmentConfig
from goose.executable_unit import ExecutableUnit
from goose.manifest import build_manifest
from goose.manifest import write_manifest
from goose.process import stream_both
from goose.process import system_python

from .base import Backend
from .base import RunResult


class PackageJson(BaseModel):
    lockfile_version: int = Field(default=3, serialization_alias="lockfileVersion")
    dependencies: Mapping[str, str]


def _bootstrap_env() -> dict[str, str]:
    return os.environ | {
        "PYTHONUNBUFFERED": "1",
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
        raise RuntimeError("Failed creating virtualenv {process.returncode=}")


async def bootstrap(
    env_path: Path,
    config: EnvironmentConfig,
) -> None:
    print(f"Creating node env at {env_path.name}", file=sys.stderr)
    await _create_node_env(env_path, config.ecosystem.version)


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
    package_json_path.write_text(package_json.model_dump_json(by_alias=True))
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
) -> None:
    lock_files_path.mkdir(exist_ok=True)

    package_json_path = _write_package_json(config, lock_files_path)

    with cd_to(lock_files_path):
        process = await asyncio.create_subprocess_exec(
            env_path / "bin" / "npm",
            *(
                "install",
                "--package-lock-only",
            ),
            env=os.environ | {"PATH": f"{os.environ['PATH']}:{env_path / 'bin'}"},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await stream_both(process)
        await process.wait()

    if process.returncode != 0:
        raise RuntimeError("Failed freezing dependencies {process.returncode=}")

    package_lock_json_path = lock_files_path / "package-lock.json"
    manifest = build_manifest(
        source_ecosystem=config.ecosystem,
        source_dependencies=config.dependencies,
        lock_files=(
            package_json_path,
            package_lock_json_path,
        ),
        lock_files_path=lock_files_path,
    )
    write_manifest(lock_files_path, manifest)


async def sync(
    env_path: Path,
    config: EnvironmentConfig,
    lock_files_path: Path,
) -> None:
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
            env=os.environ | {"PATH": f"{os.environ['PATH']}:{env_path / 'bin'}"},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await stream_both(process)
        await process.wait()

    if process.returncode != 0:
        raise RuntimeError("Failed syncing dependencies {process.returncode=}")


async def run(
    env_path: Path,
    config: EnvironmentConfig,
    unit: ExecutableUnit,
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
            "PATH": f"{os.environ['PATH']}:{env_path / 'bin'}",
        },
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await stream_both(process)
    await process.wait()

    return RunResult.ok if process.returncode == 0 else RunResult.error


backend: Final = Backend(
    ecosystem="node",
    bootstrap=bootstrap,
    freeze=freeze,
    sync=sync,
    run=run,
)
