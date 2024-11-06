import asyncio
import asyncio.subprocess
import enum
import re
from collections.abc import AsyncGenerator
from collections.abc import AsyncIterable
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from typing import assert_never

# todo: address liability
from identify.identify import tags_from_filename

from goose.process import stream_out

from .config import Config
from .config import HookConfig
from .filter import path_matches_patterns


@dataclass(frozen=True, slots=True, kw_only=True)
class Target:
    path: Path
    tags: frozenset[str]


class Selector(enum.Enum):
    all = "all"
    diff = "diff"


async def _nil_split_stream(stream: asyncio.StreamReader) -> AsyncGenerator[bytes]:
    while True:
        if stream.at_eof():
            break
        try:
            chunk = await stream.readuntil((b"\x00", b"\n"))
        except asyncio.IncompleteReadError as exc:
            if exc.expected is not None:
                raise
            break
        chunk = chunk.rstrip(b"\x00")
        chunk = chunk.strip()
        if not chunk:
            continue
        yield chunk


async def _stream_paths(stream: AsyncIterable[bytes]) -> AsyncGenerator[Path]:
    async for part in stream:
        yield Path(part.decode())


async def _git_file_list(selector: Selector) -> AsyncGenerator[Path]:
    command: Sequence[str]
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
    assert process.stdout is not None
    assert process.stderr is not None
    stream_stderr = asyncio.create_task(stream_out("[stderr]", process.stderr))
    async for path in _stream_paths(_nil_split_stream(process.stdout)):
        yield path
    await stream_stderr
    await process.wait()


_builtin_excludes: Final = (re.compile(r"^\.goose/.*"),)


async def get_targets(config: Config, selector: Selector) -> tuple[Target, ...]:
    targets = []
    async for path in _git_file_list(selector):
        if path_matches_patterns(path, (*config.exclude, *_builtin_excludes)):
            continue
        targets.append(
            Target(
                path=path,
                tags=frozenset(tags_from_filename(str(path))),
            )
        )
    return tuple(targets)


def filter_hook_targets(
    hook: HookConfig,
    targets: Sequence[Target],
) -> frozenset[Path]:
    # Send empty sequence of files for non-parameterized hooks.
    if not hook.parameterize:
        return frozenset()

    return frozenset(
        target.path
        for target in targets
        if (not hook.types or target.tags & hook.types)
        if not path_matches_patterns(target.path, hook.exclude)
    )
