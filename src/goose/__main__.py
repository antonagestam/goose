import sys
from rich.live import Live
from rich.table import Table
from rich.spinner import Spinner
from rich.text import Text

from pathlib import Path

from goose.backend.base import RunResult
from .scheduler import Scheduler, exit_code
from .context import gather_context
from .orphan_environments import probe_orphan_environments
from .environment import prepare_environment
import asyncio

from .targets import get_targets, Selector
import typer
from .asyncio import asyncio_entrypoint
from typing import Annotated, TypeAlias, Final, Optional, assert_never, Iterator

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
default_config: Final = Path("goose.yaml")


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
            return Text("[ ]", style="dim")
        case asyncio.Task():
            return spinner
        case RunResult.ok:
            return Text("[✓]", style="green")
        case RunResult.error:
            return Text("[✗]", style="red")
        case no_match:
            assert_never(no_match)


def generate_live_process_table(scheduler: Scheduler) -> Iterator[Table]:
    spinner = Table.grid()
    spinner.add_row(
        "[blue][[/blue]",
        Spinner("dots4", style="blue"),
        "[blue]][/blue]",
    )

    while True:
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
        yield hooks_table


async def display_live_table(scheduler: Scheduler) -> None:
    live_table = generate_live_process_table(scheduler)

    with Live(refresh_per_second=10) as live:
        live.update(next(live_table), refresh=True)
        async for _ in scheduler.until_complete():
            live.update(next(live_table), refresh=True)


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

    if sys.stdout.isatty():
        await display_live_table(scheduler)
    else:
        async for _ in scheduler.until_complete():
            pass

    sys.exit(exit_code(scheduler.state()))


if __name__ == "__main__":
    cli()
