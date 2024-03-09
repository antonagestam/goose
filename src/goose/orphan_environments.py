import shutil
import sys

from .context import Context


def probe_orphan_environments(context: Context, delete: bool = False) -> None:
    environment_ids = {
        environment.config.id for environment in context.environments.values()
    }
    for path in context.environments_path.glob("*"):
        if not path.is_dir():
            continue
        if path.name in environment_ids:
            continue
        if delete:
            print(f"Deleting orphan environment {path.name!r}", file=sys.stderr)
            shutil.rmtree(path)
        else:
            print(f"Warning: orphan environment {path.name!r}", file=sys.stderr)
