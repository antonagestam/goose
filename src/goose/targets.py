from __future__ import annotations

import asyncio
import asyncio.subprocess
import enum
import re
from collections.abc import AsyncGenerator
from collections.abc import AsyncIterable
from collections.abc import Callable
from collections.abc import Iterable
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from re import Pattern
from typing import Final
from typing import assert_never

# todo: address liability
from identify.identify import tags_from_filename

from goose.process import stream_out

from .config import Config
from .config import HookConfig


@dataclass(frozen=True, slots=True, kw_only=True)
class Target:
    path: Path
    tags: frozenset[str]


class Selector(enum.Enum):
    all = "all"
    diff = "diff"
    staged = "staged"


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


async def stream_paths_from_process(
    command: Sequence[str],
) -> AsyncGenerator[Path]:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert process.stdout is not None
    assert process.stderr is not None
    stream_stderr = asyncio.create_task(stream_out("[stderr]", process.stderr))
    async for path in _stream_paths(_nil_split_stream(process.stdout)):
        if not path.exists():
            continue
        yield path
    await stream_stderr
    await process.wait()


base_diff_command: Final = (
    "git",
    "diff",
    # Note: D is not included here, such that we do not pass deleted files.
    "--diff-filter=ACMR",
    "--name-only",
    "-z",
)


async def _git_file_list(selector: Selector) -> AsyncGenerator[Path]:
    command: Sequence[str]
    if selector is Selector.all:
        command = ("git", "ls-files", "-z")
    elif selector is Selector.diff:
        command = (*base_diff_command, "HEAD")
    elif selector is Selector.staged:
        command = (*base_diff_command, "--cached")
    else:
        assert_never(selector)

    async for path in stream_paths_from_process(command):
        yield path


def _path_matches_patterns(
    path: Path,
    patterns: Iterable[Pattern],
) -> bool:
    return any(pattern.search(str(path)) is not None for pattern in patterns)


def _get_path_matcher(
    exclude: Sequence[Pattern[str]],
    limit: Sequence[Pattern[str]],
) -> Callable[[Path], bool]:
    match: Callable[[Path], bool]

    if not exclude and not limit:

        def match(path: Path, /) -> bool:
            return True
    elif not limit:

        def match(
            path: Path,
            /,
            _exclude: Sequence[Pattern[str]] = exclude,
        ) -> bool:
            return not _path_matches_patterns(path, _exclude)
    elif not exclude:

        def match(
            path: Path,
            /,
            _limit: Sequence[Pattern[str]] = limit,
        ) -> bool:
            return _path_matches_patterns(path, _limit)
    else:

        def match(
            path: Path,
            /,
            _exclude: Sequence[Pattern[str]] = exclude,
            _limit: Sequence[Pattern[str]] = limit,
        ) -> bool:
            return _path_matches_patterns(path, _limit) and not _path_matches_patterns(
                path, _exclude
            )

    return match


_builtin_excludes: Final = (re.compile(r"^\.goose/.*"),)


def get_targets_from_paths(
    config: Config,
    paths: Iterable[Path],
) -> tuple[Target, ...]:
    path_is_included = _get_path_matcher(
        exclude=(*config.exclude, *_builtin_excludes),
        limit=config.limit,
    )
    return tuple(
        [
            Target(
                path=path,
                tags=frozenset(tags_from_filename(str(path))),
            )
            for path in paths
            if path_is_included(path)
        ]
    )


async def select_targets(config: Config, selector: Selector) -> tuple[Target, ...]:
    return get_targets_from_paths(
        config,
        [path async for path in _git_file_list(selector)],
    )


def filter_hook_targets(
    hook: HookConfig,
    targets: Sequence[Target],
) -> frozenset[Path]:
    # Send empty sequence of files for non-parameterized hooks.
    if not hook.parameterize:
        return frozenset()

    path_is_included = _get_path_matcher(
        exclude=hook.exclude,
        limit=hook.limit,
    )

    return frozenset(
        target.path
        for target in targets
        if (not hook.types or target.tags & hook.types)
        if path_is_included(target.path)
    )
