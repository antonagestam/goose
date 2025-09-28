import shlex
import sys
import textwrap
from pathlib import Path


def format_pre_commit_hook(
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
        "$PY" -m goose run --config "$CONFIG" --select=staged $@ < /dev/stdin
        """
    )
