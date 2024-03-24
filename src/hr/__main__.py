import sys
from rich.live import Live
from rich.table import Table
from rich.spinner import Spinner
from rich.text import Text

from pathlib import Path

from hr.backend.base import RunResult
from .scheduler import Scheduler, exit_code
from .context import gather_context
from .orphan_environments import probe_orphan_environments
from .environment import prepare_environment
import asyncio

from .targets import get_targets, Selector
import typer
from .asyncio import asyncio_entrypoint
from typing import Annotated, TypeAlias, Final, Optional, assert_never

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


cli = typer.Typer(pretty_exceptions_enable=False)


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


def format_unit_state(
    state: RunResult | asyncio.Task[RunResult] | None,
    spinner: Table,
) -> Text | Table:
    match state:
        case None:
            return Text("[W]")
        case asyncio.Task():
            return spinner
        case RunResult.ok:
            return Text("[D]", style="green")
        case RunResult.error:
            return Text("[E]", style="red")
        case no_match:
            assert_never(no_match)


@cli.command()
@asyncio_entrypoint
async def run(
    selected_hook: Optional[str] = typer.Argument(default=None),
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

    scheduler = Scheduler(
        context=ctx,
        targets=await get_targets_task,
        selected_hook=selected_hook,
    )

    spinner = Table.grid()
    spinner.add_row(
        "[blue][[/blue]",
        Spinner("dots4", style="blue"),
        "[blue]][/blue]",
    )

    with Live(refresh_per_second=10) as live:
        async for _ in scheduler.until_complete():
            hooks_table = Table(show_header=False)
            hooks_table.add_column("Hook")
            hooks_table.add_column("Processes")
            for hook, hook_units in scheduler.state().items():
                process_table = Table.grid(padding=2)
                process_table.add_row(
                    *(
                        format_unit_state(unit_state, spinner)
                        for unit, unit_state in hook_units.items()
                    )
                )
                hooks_table.add_row(hook.id, process_table)
            live.update(hooks_table, refresh=True)

    sys.exit(exit_code(scheduler.state()))


if __name__ == "__main__":
    cli()
