import asyncio
import asyncio.subprocess
from pathlib import Path
from typing import AsyncIterator

# todo: address liability
from identify.identify import tags_from_filename

from .backend._process import stream_out
from .config import Config
from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class Target:
    path: Path
    tags: frozenset[str]


async def _git_delta() -> AsyncIterator[Path]:
    process = await asyncio.create_subprocess_exec(
        "git",
        "ls-files",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stream_stderr = asyncio.create_task(stream_out("[stderr]", process.stderr))
    while not process.stdout.at_eof():
        line = await process.stdout.readline()
        if not line:
            continue
        yield Path(line.strip().decode())
    await stream_stderr


async def get_targets(config: Config) -> tuple[Target, ...]:
    targets = []
    async for path in _git_delta():
        if any(pattern.fullmatch(str(path)) for pattern in config.exclude):
            continue
        targets.append(
            Target(
                path=path,
                tags=frozenset(tags_from_filename(str(path))),
            )
        )
    return tuple(targets)
