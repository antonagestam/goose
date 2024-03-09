import os
import asyncio
import asyncio.subprocess
import sys
from contextlib import ExitStack
from functools import partial
from pathlib import Path
from typing import Final, Iterable, Sequence
from .base import Backend
from hr.config import EnvironmentConfig
from hr.manifest import build_manifest


def _system_python() -> Path:
    return Path("python")


def _venv_python(env_path: Path) -> Path:
    return env_path / "bin" / "python"


def _bootstrap_env() -> dict[str, str]:
    return os.environ | {
        "PYTHONUNBUFFERED": "1",
        "PIP_REQUIRE_VIRTUALENV": "true",
        "PIP_DISABLE_PIP_VERSION_CHECK": "true",
    }


def _run_env(env_path: Path) -> dict[str, str]:
    return os.environ | {
        "PATH": str(env_path / "bin"),
    }


async def _create_virtualenv(env_path: Path) -> None:
    process = await asyncio.create_subprocess_exec(
        _system_python(),
        *("-m", "venv", str(env_path)),
        env=_bootstrap_env(),
    )
    await process.communicate()
    if process.returncode != 0:
        raise RuntimeError("Failed creating virtualenv")


async def _stream_out(
    prefix: str,
    stream: asyncio.StreamReader,
) -> None:
    while not stream.at_eof():
        line = await stream.readline()
        if not line:
            continue
        print(prefix, line.decode(), end="", file=sys.stderr)


async def _pip_install(
    env_path: Path,
    dependencies: Iterable[str],
) -> None:
    process = await asyncio.create_subprocess_exec(
        _venv_python(env_path),
        *("-m", "pip", "install", *dependencies),
        env=_bootstrap_env(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stream_stdout = asyncio.create_task(_stream_out("[stdout]", process.stdout))
    stream_stderr = asyncio.create_task(_stream_out("[stderr]", process.stderr))
    await asyncio.gather(stream_stdout, stream_stderr)
    if process.returncode != 0:
        raise RuntimeError("Failed installing packages")


async def _pip_sync(
    env_path: Path,
    requirements_txt: Path,
) -> None:
    process = await asyncio.create_subprocess_exec(
        env_path / "bin" / "pip-sync",
        str(requirements_txt),
        env=_bootstrap_env(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stream_stdout = asyncio.create_task(_stream_out("[stdout]", process.stdout))
    stream_stderr = asyncio.create_task(_stream_out("[stderr]", process.stderr))
    await asyncio.gather(stream_stdout, stream_stderr)
    if process.returncode != 0:
        raise RuntimeError("Failed syncing dependencies")


async def bootstrap(
    env_path: Path,
    config: EnvironmentConfig,
) -> None:
    if not env_path.exists():
        print(f"Creating virtualenv {env_path.name}", file=sys.stderr)
        await _create_virtualenv(env_path)

    print("Installing pip-tools ...", file=sys.stderr)
    await _pip_install(env_path, ("pip-tools",))


async def freeze(
    env_path: Path,
    config: EnvironmentConfig,
    lock_files_path: Path,
) -> None:
    lock_files_path.mkdir(exist_ok=True)

    tmp_requirements_in = lock_files_path / "requirements.in"
    requirements_txt = lock_files_path / "requirements.txt"

    with ExitStack() as stack:
        stack.callback(partial(tmp_requirements_in.unlink, missing_ok=True))

        # Write equivalent of a requirements.in.
        with tmp_requirements_in.open("w") as fd:
            for dependency in config.dependencies:
                print(dependency, file=fd)

        process = await asyncio.create_subprocess_exec(
            env_path / "bin" / "pip-compile",
            *(
                "--upgrade",
                "--strip-extras",
                "--generate-hashes",
                "--resolver=backtracking",
                "--no-annotate",
                "--no-header",
                f"--output-file={requirements_txt}",
                f"{tmp_requirements_in}",
            ),
            env=_bootstrap_env(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stream_stdout = asyncio.create_task(_stream_out("[stdout]", process.stdout))
        stream_stderr = asyncio.create_task(_stream_out("[stderr]", process.stderr))
        await asyncio.gather(stream_stdout, stream_stderr)

    if process.returncode != 0:
        raise RuntimeError("Failed freezing dependencies")

    manifest_path = lock_files_path / "manifest.json"
    manifest = build_manifest(
        source_dependencies=config.dependencies,
        lock_files=(requirements_txt,),
        lock_files_path=lock_files_path,
    )
    manifest_path.write_text(manifest.model_dump_json())
    print(f"Wrote manifest to {manifest_path}", file=sys.stderr)


async def sync(
    env_path: Path,
    config: EnvironmentConfig,
    lock_files_path: Path,
) -> None:
    requirements_txt = lock_files_path / "requirements.txt"

    print("Syncing dependencies", file=sys.stderr)
    await _pip_sync(
        env_path=env_path,
        requirements_txt=requirements_txt,
    )


async def run(
    env_path: Path,
    config: EnvironmentConfig,
    command: Sequence[str],
) -> None:
    process = await asyncio.create_subprocess_exec(
        *command,
        env=_run_env(env_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stream_stdout = asyncio.create_task(_stream_out("[stdout]", process.stdout))
    stream_stderr = asyncio.create_task(_stream_out("[stderr]", process.stderr))
    await asyncio.gather(stream_stdout, stream_stderr)
    if process.returncode != 0:
        raise RuntimeError("Failed running command")


backend: Final = Backend(
    language="python",
    bootstrap=bootstrap,
    freeze=freeze,
    sync=sync,
    run=run,
)
