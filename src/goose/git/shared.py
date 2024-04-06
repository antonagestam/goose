import asyncio
from collections.abc import Iterator
from pathlib import Path
from types import MappingProxyType
from typing import Final

from goose.process import stream_out

GIT_ENV: Final = MappingProxyType(
    {
        # https://git-scm.com/docs/git-status#_background_refresh
        "GIT_OPTIONAL_LOCKS": "0",
    }
)


def nil_split(joined: bytes) -> Iterator[str]:
    for item in joined.strip().split(b"\x00"):
        stripped = item.strip()
        if not stripped:
            continue
        yield stripped.decode()


async def get_git_hash(path: Path) -> str:
    process = await asyncio.create_subprocess_exec(
        "git",
        "hash-object",
        path,
        env=GIT_ENV,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert process.stdout is not None
    assert process.stderr is not None
    stream_stderr = asyncio.create_task(stream_out("[stderr]", process.stderr))

    while not process.stdout.at_eof():
        line = (await process.stdout.readline()).strip()
        if line:
            break
    else:
        raise RuntimeError(f"Failed getting hash-object for file {path!s}")

    await stream_stderr
    await process.wait()

    return line.decode()
