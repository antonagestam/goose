import sys
from pathlib import Path

from .config import load_config
from .environment import Environment, probe_orphans
import asyncio


@asyncio.run
@lambda fn: fn()
async def main() -> None:
    config = load_config(Path("config.yaml"))

    lock_files_path = Path("./hr-locks")
    lock_files_path.mkdir(exist_ok=True)

    env_dir = Path("./envs").resolve()
    env_dir.mkdir(exist_ok=True)

    environments = {
        cfg.id: Environment(cfg, env_dir, lock_files_path)
        for cfg in config.environments
    }

    probe_orphans(environments, env_dir, delete=False)

    bootstrap_tasks = [
        asyncio.create_task(environment.bootstrap())
        for environment in environments.values()
    ]
    await asyncio.gather(*bootstrap_tasks)
    print("Bootstrapping done", file=sys.stderr)

    freeze_tasks = [
        asyncio.create_task(environment.freeze())
        for environment in environments.values()
    ]
    await asyncio.gather(*freeze_tasks)
    print("Freezing done", file=sys.stderr)

    sync_tasks = [
        asyncio.create_task(environment.sync())
        for environment in environments.values()
    ]
    await asyncio.gather(*sync_tasks)
    print("Sync done", file=sys.stderr)

    for hook in config.hooks:
        print(f"{hook=}")
        environment = environments[hook.environment]
        await environment.run(hook.command.split(" "))
