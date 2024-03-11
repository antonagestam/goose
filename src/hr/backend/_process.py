import asyncio
from pathlib import Path
import sys


def system_python() -> Path:
    return Path(sys.executable)


async def stream_out(
    prefix: str,
    stream: asyncio.StreamReader,
) -> None:
    while not stream.at_eof():
        line = await stream.readline()
        if not line:
            continue
        print(prefix, line.decode(), end="", file=sys.stderr)


async def stream_both(process: asyncio.subprocess.Process) -> None:
    stream_stdout = asyncio.create_task(stream_out("[stdout]", process.stdout))
    stream_stderr = asyncio.create_task(stream_out("[stderr]", process.stderr))
    await asyncio.gather(stream_stdout, stream_stderr)
