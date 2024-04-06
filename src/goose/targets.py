import asyncio
import asyncio.subprocess
import enum
import re
from collections.abc import AsyncIterator
from collections.abc import Iterator
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
from .git.shared import nil_split


@dataclass(frozen=True, slots=True, kw_only=True)
class Target:
    path: Path
    tags: frozenset[str]


class Selector(enum.Enum):
    all = "all"
    diff = "diff"


def _split_git_path_line(paths: bytes) -> Iterator[Path]:
    for part in nil_split(paths):
        yield Path(part)


async def _git_file_list(selector: Selector) -> AsyncIterator[Path]:
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
    while not process.stdout.at_eof():
        line = await process.stdout.readline()
        if not line:
            continue
        for path in _split_git_path_line(line):
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
