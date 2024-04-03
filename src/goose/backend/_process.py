import asyncio
import sys
from pathlib import Path


def system_python() -> Path:
    return Path(sys.executable)


async def stream_out(
    prefix: bytes,
    stream: asyncio.StreamReader,
) -> None:
    while not stream.at_eof():
        line = await stream.readline()
        if not line:
            continue
        sys.stderr.buffer.write(prefix)
        sys.stderr.buffer.write(line)


async def stream_both(process: asyncio.subprocess.Process) -> None:
    assert process.stdout is not None
    assert process.stderr is not None
    stream_stdout = asyncio.create_task(stream_out(b"[stdout] ", process.stdout))
    stream_stderr = asyncio.create_task(stream_out(b"[stderr] ", process.stderr))
    await asyncio.gather(stream_stdout, stream_stderr)
