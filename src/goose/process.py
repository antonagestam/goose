import asyncio
import sys
from pathlib import Path
from typing import IO


def system_python() -> Path:
    return Path(sys.executable)


async def stream_out(
    prefix: str,
    stream: asyncio.StreamReader,
    file: IO[str] = sys.stderr,
) -> None:
    while not stream.at_eof():
        line = await stream.readline()
        if not line:
            continue
        print(prefix, line.decode(), end="", file=file)


async def stream_both(
    process: asyncio.subprocess.Process,
    prefix: str = "",
    file: IO[str] = sys.stderr,
) -> None:
    assert process.stdout is not None
    assert process.stderr is not None
    stream_stdout = asyncio.create_task(
        stream_out(f"{prefix}[stdout]", process.stdout, file)
    )
    stream_stderr = asyncio.create_task(
        stream_out(f"{prefix}[stderr]", process.stderr, file)
    )
    await asyncio.gather(stream_stdout, stream_stderr)
