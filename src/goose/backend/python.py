import asyncio
import asyncio.subprocess
import os
import sys
from collections.abc import Iterable
from contextlib import ExitStack
from pathlib import Path
from typing import Final

from goose.config import EnvironmentConfig
from goose.executable_unit import ExecutableUnit
from goose.manifest import build_manifest
from goose.manifest import write_manifest
from goose.process import stream_both
from goose.process import system_python

from .base import Backend
from .base import RunResult


def _venv_python(env_path: Path) -> Path:
    return env_path / "bin" / "python"


def _bootstrap_env() -> dict[str, str]:
    return os.environ | {
        "PYTHONUNBUFFERED": "1",
        "PIP_REQUIRE_VIRTUALENV": "true",
        "PIP_DISABLE_PIP_VERSION_CHECK": "true",
    }


async def _create_virtualenv(env_path: Path, version: str) -> None:
    process = await asyncio.create_subprocess_exec(
        system_python(),
        "-m",
        "uv",
        "venv",
        "--no-project",
        "--python-preference=only-managed",
        f"--python={version}",
        str(env_path),
        env=_bootstrap_env(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await stream_both(process)
    await process.wait()
    if process.returncode != 0:
        raise RuntimeError("Failed creating virtualenv {process.returncode=}")


async def _pip_install(
    env_path: Path,
    dependencies: Iterable[str],
) -> None:
    process = await asyncio.create_subprocess_exec(
        "uv",
        "pip",
        "install",
        f"--python={_venv_python(env_path)}",
        *dependencies,
        env=_bootstrap_env(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await stream_both(process)
    await process.wait()
    if process.returncode != 0:
        raise RuntimeError("Failed installing packages {process.returncode=}")


async def _pip_sync(
    env_path: Path,
    requirements_txt: Path,
) -> None:
    process = await asyncio.create_subprocess_exec(
        system_python(),
        "-m",
        "uv",
        "pip",
        "sync",
        f"--python={_venv_python(env_path)}",
        str(requirements_txt),
        env=_bootstrap_env(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await stream_both(process)
    await process.wait()
    if process.returncode != 0:
        raise RuntimeError("Failed syncing dependencies {process.returncode=}")


async def bootstrap(
    env_path: Path,
    config: EnvironmentConfig,
) -> None:
    print(f"Creating virtualenv {env_path.name}", file=sys.stderr)
    await _create_virtualenv(env_path, config.ecosystem.version)


async def freeze(
    env_path: Path,
    config: EnvironmentConfig,
    lock_files_path: Path,
) -> None:
    lock_files_path.mkdir(exist_ok=True)

    tmp_requirements_in = lock_files_path / "requirements.in"
    requirements_txt = lock_files_path / "requirements.txt"

    with ExitStack() as stack:
        stack.callback(tmp_requirements_in.unlink, missing_ok=True)

        # Write equivalent of a requirements.in.
        with tmp_requirements_in.open("w") as fd:
            for dependency in config.dependencies:
                print(dependency, file=fd)

        process = await asyncio.create_subprocess_exec(
            system_python(),
            "-m",
            "uv",
            "pip",
            "compile",
            f"--python={_venv_python(env_path)}",
            "--upgrade",
            "--strip-extras",
            "--generate-hashes",
            "--no-annotate",
            "--no-header",
            f"--output-file={requirements_txt}",
            f"{tmp_requirements_in}",
            env=_bootstrap_env(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await stream_both(process)
        await process.wait()

    if process.returncode != 0:
        raise RuntimeError("Failed freezing dependencies {process.returncode=}")

    manifest = build_manifest(
        source_ecosystem=config.ecosystem,
        source_dependencies=config.dependencies,
        lock_files=(requirements_txt,),
        lock_files_path=lock_files_path,
    )
    write_manifest(lock_files_path, manifest)


async def sync(
    env_path: Path,
    config: EnvironmentConfig,
    lock_files_path: Path,
) -> None:
    requirements_txt = lock_files_path / "requirements.txt"

    await _pip_sync(
        env_path=env_path,
        requirements_txt=requirements_txt,
    )


async def run(
    env_path: Path,
    config: EnvironmentConfig,
    unit: ExecutableUnit,
) -> RunResult:
    bin_path = env_path / "bin"
    process = await asyncio.create_subprocess_exec(
        unit.hook.command,
        *unit.hook.args,
        *unit.targets,
        env={
            **os.environ,
            **dict(unit.hook.env_vars),
            "PATH": f"{bin_path}:{os.environ['PATH']}",
        },
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await stream_both(process)
    await process.wait()

    return RunResult.ok if process.returncode == 0 else RunResult.error


backend: Final = Backend(
    ecosystem="python",
    bootstrap=bootstrap,
    freeze=freeze,
    sync=sync,
    run=run,
)
