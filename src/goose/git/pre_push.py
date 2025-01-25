import asyncio
import enum
import shlex
import sys
import textwrap
from collections.abc import AsyncGenerator
from collections.abc import Generator
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO
from typing import assert_never
from typing import final

from goose.process import stream_out
from goose.targets import base_diff_command
from goose.targets import stream_paths_from_process


def format_pre_push_hook(
    config_path: Path,
    _executable: str = sys.executable,
) -> str:
    escaped_config_path = shlex.quote(str(config_path))
    escaped_executable = shlex.quote(_executable)
    return textwrap.dedent(
        f"""\
        #!/bin/sh
        set -e
        export PYTHONUNBUFFERED=1
        PY={escaped_executable}
        CONFIG={escaped_config_path}
        "$PY" -m goose exec-pre-push --config "$CONFIG" $@ < /dev/stdin
        """
    )


class ObjectHashSentinel(enum.Enum):
    zero = "0" * 40


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class PushDelete:
    remote_ref: str
    remote_oid: str


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class PushNew:
    local_ref: str
    local_oid: str
    remote_ref: str


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class PushUpdate:
    local_ref: str
    local_oid: str
    remote_ref: str
    remote_oid: str


type PushEvent = PushDelete | PushNew | PushUpdate


def parse_push_events(
    input_stream: IO[str],
) -> Generator[PushEvent]:
    for line in input_stream:
        match line.strip().split(maxsplit=4):
            case (_, ObjectHashSentinel.zero.value, remote_ref, remote_oid):
                yield PushDelete(
                    remote_ref=remote_ref,
                    remote_oid=remote_oid,
                )
            case (local_ref, local_oid, remote_ref, ObjectHashSentinel.zero.value):
                yield PushNew(
                    local_ref=local_ref,
                    local_oid=local_oid,
                    remote_ref=remote_ref,
                )
            case (local_ref, local_oid, remote_ref, remote_oid):
                yield PushUpdate(
                    local_ref=local_ref,
                    local_oid=local_oid,
                    remote_ref=remote_ref,
                    remote_oid=remote_oid,
                )
            case no_match:
                raise ValueError(
                    f"Failed to parse pre-push change event from stdin. Failing line: "
                    f"{no_match!r}."
                )


async def stream_revs_from_process(
    command: Sequence[str],
) -> AsyncGenerator[str]:
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert process.stdout is not None
    assert process.stderr is not None
    stream_stderr = asyncio.create_task(stream_out("[stderr]", process.stderr))

    while True:
        if process.stdout.at_eof():
            break
        line = (await process.stdout.readline()).decode().strip()
        if not line:
            continue
        yield line

    await stream_stderr
    await process.wait()


async def _list_new_branch_files(
    remote: str,
    local_oid: str,
) -> frozenset[Path]:
    return frozenset(
        {
            path
            async for revision in stream_revs_from_process(
                (
                    "git",
                    "rev-list",
                    local_oid,
                    "--topo-order",
                    "--reverse",
                    "--not",
                    f"--remotes={remote}",
                )
            )
            async for path in stream_paths_from_process(
                (
                    "git",
                    "show",
                    "--name-only",
                    "--pretty=",
                    "-z",
                    revision,
                )
            )
        }
    )


async def _list_updated_branch_files(
    remote_oid: str,
    local_oid: str,
) -> frozenset[Path]:
    return frozenset(
        {
            path
            async for path in stream_paths_from_process(
                (
                    *base_diff_command,
                    f"{remote_oid}..{local_oid}",
                )
            )
        }
    )


async def get_paths_for_event(
    remote: str,
    event: PushNew | PushUpdate,
) -> frozenset[Path]:
    match event:
        case PushNew(local_oid=local_oid):
            return await _list_new_branch_files(remote, local_oid)
        case PushUpdate(remote_oid=remote_oid, local_oid=local_oid):
            return await _list_updated_branch_files(remote_oid, local_oid)
        case no_match:
            assert_never(no_match)
