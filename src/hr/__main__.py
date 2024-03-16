import sys
from pathlib import Path

from .config import load_config
from .environment import (
    probe_orphan_environments,
    build_environments,
    prepare_environment,
)
import asyncio

from .targets import get_targets
from .paths import get_env_path
import typer
from .asyncio import asyncio_entrypoint
from typing import Annotated, TypeAlias, Final

ConfigOption: TypeAlias = Annotated[
    Path,
    typer.Option(
        "--config",
        resolve_path=True,
        readable=True,
        exists=True,
        dir_okay=False,
    ),
]
default_config: Final = Path("config.yaml")


cli = typer.Typer()


@cli.command()
@asyncio_entrypoint
async def upgrade(
    config_path: ConfigOption = default_config,
) -> None:
    config = load_config(config_path)
    lock_files_path = Path("./hr-locks")
    lock_files_path.mkdir(exist_ok=True)
    env_dir = get_env_path()
    environments = build_environments(config, env_dir, lock_files_path)
    await asyncio.gather(*[
        asyncio.create_task(prepare_environment(environment, upgrade=True))
        for environment in environments.values()
    ])
    print("All environments up-to-date", file=sys.stderr)


@cli.command()
@asyncio_entrypoint
async def run(
    config_path: ConfigOption = default_config,
    delete_orphan_environments: bool = False,
) -> None:
    config = load_config(config_path)

    lock_files_path = Path("./hr-locks")
    lock_files_path.mkdir(exist_ok=True)

    # Spawn file delta task to run in background.
    get_targets_task = asyncio.create_task(get_targets(config))

    env_dir = get_env_path()

    environments = build_environments(config, env_dir, lock_files_path)

    probe_orphan_environments(environments, env_dir, delete=delete_orphan_environments)

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


if __name__ == "__main__":
    cli()
