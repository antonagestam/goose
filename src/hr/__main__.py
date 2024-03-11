import sys
from pathlib import Path

from .config import load_config
from .environment import probe_orphans, build_environments, prepare_environment
import asyncio


@asyncio.run
@lambda fn: fn()
async def main() -> None:
    config = load_config(Path("config.yaml"))

    lock_files_path = Path("./hr-locks")
    lock_files_path.mkdir(exist_ok=True)

    env_dir = Path("./envs").resolve()
    env_dir.mkdir(exist_ok=True)

    environments = build_environments(config, env_dir, lock_files_path)

    probe_orphans(environments, env_dir, delete=False)

    prepare_tasks = [
        asyncio.create_task(prepare_environment(environment))
        for environment in environments.values()
    ]

    # fixme: Should allow starting hooks before all environments are ready.
    await asyncio.gather(*prepare_tasks)
    print("All environments ready", file=sys.stderr)

    for hook in config.hooks:
        print(f"{hook=}")
        environment = environments[hook.environment]
        await environment.run(hook)
