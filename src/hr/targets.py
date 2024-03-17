import asyncio
import asyncio.subprocess
import enum
from pathlib import Path
from typing import AsyncIterator, Iterator, assert_never

# todo: address liability
from identify.identify import tags_from_filename

from .backend._process import stream_out
from .config import Config
from dataclasses import dataclass

from .filter import path_matches_patterns


@dataclass(frozen=True, slots=True, kw_only=True)
class Target:
    path: Path
    tags: frozenset[str]


def _split_git_path_line(paths: bytes) -> Iterator[Path]:
    for path in paths.strip().split(b"\x00"):
        if not path:
            continue
        yield Path(path.decode())


class Selector(enum.Enum):
    all = "all"
    diff = "diff"


async def _git_file_list(selector: Selector) -> AsyncIterator[Path]:
    if selector is Selector.all:
        command = ("git", "ls-files", "-z")
    elif selector is Selector.diff:
        command = (
            "git",
            "diff",
            "--name-only",
            "-z",
            "HEAD",
        )
    else:
        assert_never(selector)

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stream_stderr = asyncio.create_task(stream_out("[stderr]", process.stderr))
    while not process.stdout.at_eof():
        line = await process.stdout.readline()
        if not line:
            continue
        for path in _split_git_path_line(line):
            yield path
    await stream_stderr
    await process.wait()


async def get_targets(config: Config, selector: Selector) -> tuple[Target, ...]:
    targets = []
    async for path in _git_file_list(selector):
        if path_matches_patterns(path, config.exclude):
            continue
        targets.append(
            Target(
                path=path,
                tags=frozenset(tags_from_filename(str(path))),
            )
        )
    return tuple(targets)
