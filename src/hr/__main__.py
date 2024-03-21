import sys
from collections.abc import Set
from pathlib import Path

from .config import HookConfig
from .parallel import all_targets, RunningHook
from .context import gather_context, Context
from .orphan_environments import probe_orphan_environments
from .environment import (
    prepare_environment,
)
import asyncio

from .targets import get_targets, Selector, filter_hook_targets
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


def spawn(
    hook: HookConfig,
    ctx: Context,
    targets: Set[Path],
) -> RunningHook:
    print(f"[{hook.environment}] [{hook.id}]", file=sys.stderr)
    environment = ctx.environments[hook.environment]
    task = asyncio.create_task(environment.run(hook, targets))
    return RunningHook(
        config=hook,
        task=task,
        targets=targets,
    )


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

    running_hooks = []
    remaining_hooks = list(ctx.config.hooks)

    while True:
        for i, hook in enumerate(remaining_hooks):
            hook_targets = filter_hook_targets(hook, targets)

            # If no other task running, start.
            if not running_hooks:
                running_hooks.append(spawn(hook, ctx, hook_targets))
                del remaining_hooks[i]
                continue

            # If running tasks have disjoint set of files vs current, start.
            running_file_set = all_targets(running_hooks)
            if not hook_targets & running_file_set:
                running_hooks.append(spawn(hook, ctx, hook_targets))
                del remaining_hooks[i]
                continue

            # If running tasks overlap with current, but neither mutates, start.
            if hook.read_only and all(
                running_hook.config for running_hook in running_hooks
            ):
                running_hooks.append(spawn(hook, ctx, hook_targets))
                del remaining_hooks[i]
                continue

        if not remaining_hooks:
            break

        # Await first finished task.
        await asyncio.wait(
            (running_hook.task for running_hook in running_hooks),
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Filter completed tasks.
        running_hooks = [
            running_hook
            for running_hook in running_hooks
            if not running_hook.task.done()
        ]

    await asyncio.wait(
        (running_hook.task for running_hook in running_hooks),
        return_when=asyncio.ALL_COMPLETED,
    )


if __name__ == "__main__":
    cli()
