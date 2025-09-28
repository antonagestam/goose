import asyncio
import asyncio.subprocess
import os
import sys
from collections.abc import Iterable
from contextlib import ExitStack
from io import StringIO
from pathlib import Path
from typing import IO
from typing import Final

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


def _venv_python(env_path: Path) -> Path:
    return env_path / "bin" / "python"


def _bootstrap_env() -> dict[str, str]:
    return os.environ | {
        "PYTHONUNBUFFERED": "1",
        "PIP_REQUIRE_VIRTUALENV": "true",
        "PIP_DISABLE_PIP_VERSION_CHECK": "true",
    }


async def _create_virtualenv(env_path: Path, version: str | None) -> None:
    process = await asyncio.create_subprocess_exec(
        system_python(),
        "-m",
        "uv",
        "venv",
        "--no-project",
        "--python-preference=only-managed",
        *([f"--python={version}"] if version is not None else []),
        str(env_path),
        env=_bootstrap_env(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await stream_both(process)
    await process.wait()
    if process.returncode != 0:
        raise RuntimeError("Failed creating virtualenv {process.returncode=}")


async def _spawn_version_process(env_path: Path) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        _venv_python(env_path),
        "--version",
        env=_bootstrap_env(),
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
        raise RuntimeError(f"Failed getting version from venv {process.returncode=}")
    ecosystem_version = version_buffer.getvalue().strip().removeprefix("Python ")
    if configured_version is not None and not ecosystem_version.startswith(
        configured_version
    ):
        raise RuntimeError(
            f"Resulting version of venv ({ecosystem_version}) does not match "
            f"environment config ({configured_version})"
        )
    return ecosystem_version


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
    manifest: LockManifest | None,
) -> InitialState:
    configured_version = get_ecosystem_version(config.ecosystem)
    version = (
        # fixme: should call `uv python upgrade [request_version]` here!
        configured_version if manifest is None else manifest.ecosystem_version
    )

    print(
        f"Creating virtualenv {env_path.name} with version {version}", file=sys.stderr
    )
    await _create_virtualenv(env_path, version)
    bootstrapped_version = await _gather_version_process(
        await _spawn_version_process(env_path),
        configured_version,
    )

    return InitialState(
        stage=InitialStage.bootstrapped,
        ecosystem=config.ecosystem,
        bootstrapped_version=bootstrapped_version,
    )


async def freeze(
    env_path: Path,
    config: EnvironmentConfig,
    lock_files_path: Path,
) -> tuple[InitialState, LockManifest]:
    tmp_requirements_in = lock_files_path / "requirements.in"
    requirements_txt = lock_files_path / "requirements.txt"

    version_process = await _spawn_version_process(env_path)

    with ExitStack() as stack:
        stack.callback(tmp_requirements_in.unlink, missing_ok=True)

        # Write equivalent of a requirements.in.
        with tmp_requirements_in.open("w") as fd:
            for dependency in config.dependencies:
                print(dependency, file=fd)

        compile_process = await asyncio.create_subprocess_exec(
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
        await stream_both(compile_process)
        await compile_process.wait()

    if compile_process.returncode != 0:
        raise RuntimeError(
            f"Failed freezing dependencies {compile_process.returncode=}"
        )

    bootstrapped_version = await _gather_version_process(
        version_process,
        get_ecosystem_version(config.ecosystem),
    )

    state = InitialState(
        stage=InitialStage.frozen,
        ecosystem=config.ecosystem,
        bootstrapped_version=bootstrapped_version,
    )
    manifest = build_manifest(
        source_ecosystem=config.ecosystem,
        source_dependencies=config.dependencies,
        lock_files=(requirements_txt,),
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
    requirements_txt = lock_files_path / "requirements.txt"
    version_process = await _spawn_version_process(env_path)
    await _pip_sync(
        env_path=env_path,
        requirements_txt=requirements_txt,
    )
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
    await stream_both(process, file=buffer, prefix=unit.log_prefix)
    await process.wait()
    return RunResult.ok if process.returncode == 0 else RunResult.error


backend: Final = Backend(
    ecosystem="python",
    bootstrap=bootstrap,
    freeze=freeze,
    sync=sync,
    run=run,
)
