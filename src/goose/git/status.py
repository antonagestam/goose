from __future__ import annotations

import asyncio
import enum
from collections.abc import AsyncIterator
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from goose.process import stream_out

from .shared import GIT_ENV
from .shared import get_git_hash
from .shared import nil_split


class ChangeKind(enum.Enum):
    modified = "1"
    renamed = "2"
    unmerged = "u"


# fmt: off
_read_fs_codes = frozenset({
    # Not updated.
    ".A", ".M",
    # Updated in index.
    "MM", "MT",
    # Type changed in index.
    "TM", "TT",
    # Added to index.
    "AM", "AT",
    # Renamed in index.
    "RM", "RT",
    # Copied in index.
    "CM", "CT",
    # Type changed in work tree since index.
    ".T",
    # Renamed in worktree.
    ".R",
    # Copied in worktree.
    ".C",
})
_use_index_codes = frozenset({
    # Index and worktree matches.
    "M.", "T.", "A.", "R.", "C.",
})
_skip_codes = frozenset({
    # Deleted in worktree.
    ".D", "MD", "TD", "AD", "RD", "CD",
    # Deleted from index.
    "D.",
})
# fmt: on
# todo: unit test
assert not _read_fs_codes & _use_index_codes, _read_fs_codes & _use_index_codes
assert not _skip_codes & _use_index_codes
assert not _skip_codes & _read_fs_codes, _skip_codes & _read_fs_codes


@dataclass(frozen=True, slots=True, kw_only=True, order=True)
class ChangedFile:
    path: Path
    head_object_name: str
    index_object_name: str
    worktree_object_name: str


async def _changed_files_from_output(output: bytes) -> AsyncIterator[ChangedFile]:
    nil_parts = nil_split(output)
    for entry in nil_parts:
        (
            change_part,
            status_part,
            submodule_state,
            _head_mode,
            _index_mode,
            _worktree_mode,
            head_object_name,
            index_object_name,
            *_,
            path_part,
        ) = entry.split(" ")

        if submodule_state != "N...":
            raise NotImplementedError("Submodules are not supported")

        path = Path(path_part)
        change = ChangeKind(change_part)
        if change is ChangeKind.unmerged:
            continue
        elif change is ChangeKind.renamed:
            # Consume original path.
            next(nil_parts)

        if status_part in _read_fs_codes:
            worktree_object_name = await get_git_hash(path)
        elif status_part in _use_index_codes:
            worktree_object_name = index_object_name
        elif status_part in _skip_codes:
            continue
        else:
            raise NotImplementedError(f"Unexpected file status: {status_part}")

        yield ChangedFile(
            path=path,
            head_object_name=head_object_name,
            index_object_name=index_object_name,
            worktree_object_name=worktree_object_name,
        )


async def _parse_changed_files(
    stream: asyncio.StreamReader,
) -> AsyncIterator[ChangedFile]:
    while not stream.at_eof():
        line = await stream.readline()
        if not line:
            continue
        # Ignore headers and untracked and ignored files.
        if line.startswith((b"#", b"!", b"?")):
            continue

        async for changed_file in _changed_files_from_output(line):
            yield changed_file


async def get_git_status(targets: Iterable[Path]) -> tuple[ChangedFile, ...]:
    process = await asyncio.create_subprocess_exec(
        "git",
        "status",
        # https://git-scm.com/docs/git-status#_untracked_files_and_performance
        "--untracked-files=no",
        # https://git-scm.com/docs/git-status#_porcelain_format_version_2
        "--porcelain=v2",
        # https://git-scm.com/docs/git-status#_pathname_format_notes_and_z
        "-z",
        "--",
        *targets,
        env=GIT_ENV,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert process.stdout is not None
    assert process.stderr is not None
    stream_stderr = asyncio.create_task(stream_out("[stderr]", process.stderr))

    changed_files = []
    async for changed_file in _parse_changed_files(process.stdout):
        changed_files.append(changed_file)

    await stream_stderr
    await process.wait()

    return tuple(sorted(changed_files))
