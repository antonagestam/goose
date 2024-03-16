import sys
from pathlib import Path

from .context import gather_context
from .orphan_environments import probe_orphan_environments
from .environment import (
    prepare_environment,
)
import asyncio

from .targets import get_targets, Selector
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
    ctx = gather_context(config_path)
    await asyncio.gather(
        *[
            asyncio.create_task(prepare_environment(environment, upgrade=True))
            for environment in ctx.environments.values()
        ]
    )
    print("All environments up-to-date", file=sys.stderr)


@cli.command()
@asyncio_entrypoint
async def run(
    config_path: ConfigOption = default_config,
    delete_orphan_environments: bool = False,
    select: Selector = typer.Option(default="diff"),
) -> None:
    ctx = gather_context(config_path)

    # Spawn file delta task to run in background.
    get_targets_task = asyncio.create_task(get_targets(ctx.config, select))

    probe_orphan_environments(ctx, delete=delete_orphan_environments)

    prepare_tasks = [
        asyncio.create_task(prepare_environment(environment))
        for environment in ctx.environments.values()
    ]

    # fixme: Should allow starting hooks before all environments are ready.
    await asyncio.gather(*prepare_tasks)
    print("All environments ready", file=sys.stderr)

    targets = await get_targets_task

    for hook in ctx.config.hooks:
        print(f"[{hook.environment}] [{hook.id}]", file=sys.stderr)
        environment = ctx.environments[hook.environment]
        await environment.run(hook, targets)


if __name__ == "__main__":
    cli()
