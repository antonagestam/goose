import sys
from pathlib import Path

from .config import load_config
from .environment import probe_orphans, build_environments, prepare_environment
import asyncio

from .targets import get_targets
from .paths import get_env_path


@asyncio.run
@lambda fn: fn()
async def main() -> None:
    config = load_config(Path("config.yaml"))

    lock_files_path = Path("./hr-locks")
    lock_files_path.mkdir(exist_ok=True)

    # Spawn file delta task to run in background.
    get_targets_task = asyncio.create_task(get_targets(config))

    env_dir = get_env_path()

    environments = build_environments(config, env_dir, lock_files_path)

    probe_orphans(environments, env_dir, delete=False)

    prepare_tasks = [
        asyncio.create_task(prepare_environment(environment))
        for environment in environments.values()
    ]

    # fixme: Should allow starting hooks before all environments are ready.
    await asyncio.gather(*prepare_tasks)
    print("All environments ready", file=sys.stderr)

    targets = await get_targets_task

    for hook in config.hooks:
        print(f"[{hook.environment}] [{hook.id}]", file=sys.stderr)
        environment = environments[hook.environment]
        await environment.run(hook, targets)
