import asyncio
import enum
import sys
import time
from collections.abc import Collection
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated
from typing import Final
from typing import Optional
from typing import TypeAlias
from typing import assert_never

import typer
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from goose.backend.base import RunResult
from goose.config import HookConfig

from .asyncio import asyncio_entrypoint
from .context import gather_context
from .environment import NeedsFreeze
from .environment import prepare_environment
from .orphan_environments import probe_orphan_environments
from .scheduler import Scheduler
from .scheduler import UnitFinished
from .scheduler import UnitScheduled
from .targets import Selector
from .targets import get_targets

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
        case RunResult.modified:
            return Text("[✎]", style="red")
        case no_match:
            assert_never(no_match)


def format_hook_name(
    hook: HookConfig,
    states: Collection[RunResult | asyncio.Task[RunResult] | None],
) -> Text:
    if RunResult.error in states:
        return Text(hook.id, style="red")
    if any(isinstance(state, asyncio.Task) for state in states):
        return Text(hook.id)
    if RunResult.ok in states:
        return Text(hook.id, style="green")
    return Text(hook.id, style="dim")


def generate_live_process_table(scheduler: Scheduler) -> Iterator[Panel]:
    spinner = Table.grid()
    spinner.add_row(
        "[blue][[/blue]",
        Spinner("dots4", style="blue"),
        "[blue]][/blue]",
    )

    while True:
        hooks_table = Table(
            show_header=False,
            show_edge=False,
        )
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
            hooks_table.add_row(
                format_hook_name(hook, hook_units.values()),
                process_table,
            )
        yield Panel(
            hooks_table,
            title="Running hooks",
            border_style="magenta",
        )


async def display_live_table(scheduler: Scheduler) -> None:
    live_table = generate_live_process_table(scheduler)

    with Live(refresh_per_second=10) as live:
        live.update(next(live_table), refresh=True)
        async for _ in scheduler.until_complete():
            live.update(next(live_table), refresh=True)


def print_summary(console: Console, scheduler: Scheduler) -> None:
    any_error = False
    any_modified = False
    for units in scheduler.state().values():
        for unit_state in units.values():
            if unit_state is RunResult.error:
                any_error = True
            elif unit_state is RunResult.modified:
                any_modified = True
        if any_error and any_modified:
            break

    if any_error:
        console.print("Some hooks errored.", style="red")
    if any_modified:
        console.print("Some hooks made changes.", style="red")
    if any_error or any_modified:
        sys.exit(1)

    console.print("All ok!", style="green")


@cli.command()
@asyncio_entrypoint
async def run(
    selected_hook: Optional[str] = typer.Argument(default=None),  # noqa
    config_path: ConfigOption = default_config,
    delete_orphan_environments: bool = False,
    select: Selector = typer.Option(default="diff"),
) -> None:
    console = Console(stderr=True)
    ctx = gather_context(config_path)

    probe_orphan_environments(ctx, delete=delete_orphan_environments)

    prepare_tasks = [
        asyncio.create_task(prepare_environment(environment))
        for environment in ctx.environments.values()
    ]
    done, pending = await asyncio.wait(
        prepare_tasks,
        return_when=asyncio.FIRST_EXCEPTION,
    )
    for task in done:
        try:
            task.result()
        except NeedsFreeze:
            console.print(
                "Missing lock files, run `goose upgrade` first.",
                style="red",
            )
            sys.exit(1)

    print("All environments ready", file=sys.stderr)

    scheduler = Scheduler(
        context=ctx,
        targets=await get_targets(ctx.config, select),
        selected_hook=selected_hook,
    )

    if sys.stdout.isatty():
        await display_live_table(scheduler)
    else:
        async for event in scheduler.until_complete():
            t = time.time_ns()
            if isinstance(event, UnitScheduled):
                print(
                    f"[{event.unit.hook.id}@{event.unit.id}] [{t}] Unit scheduled",
                    file=sys.stderr,
                )
            elif isinstance(event, UnitFinished):
                print(
                    f"[{event.unit.hook.id}@{event.unit.id}] [{t}] Unit finished: {event.result.name}",
                    file=sys.stderr,
                )
            else:
                assert_never(event)

    print_summary(console, scheduler)


template = """\
#!/usr/bin/env bash
set -euo pipefail
python -m goose run '--config={config_path}'
"""


class GitHookType(enum.Enum):
    pre_commit = "pre-commit"
    pre_push = "pre-push"


@cli.command()
@asyncio_entrypoint
async def git_hook(
    hook: GitHookType,
    config_path: ConfigOption = default_config,
) -> None:
    hooks_path = Path(".git/hooks")
    assert hooks_path.exists()
    assert hooks_path.is_dir()
    hook_path = hooks_path / hook.value
    hook_path.write_text(template.format(config_path=str(config_path)))
    hook_path.chmod(0o755)


if __name__ == "__main__":
    cli()
