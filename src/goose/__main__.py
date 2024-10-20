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
from goose.config import EnvironmentId
from goose.config import HookConfig

from . import __version__
from .asyncio import asyncio_entrypoint
from .context import gather_context
from .environment import Environment
from .environment import InitialState
from .environment import NeedsFreeze
from .environment import SyncedState
from .environment import UninitializedState
from .environment import prepare_environment
from .orphan_environments import probe_orphan_environments
from .scheduler import Scheduler
from .scheduler import UnitFinished
from .scheduler import UnitScheduled
from .targets import Selector
from .targets import filter_hook_targets
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


@cli.command()
@asyncio_entrypoint
async def environment(
    selected_environment: Optional[str] = typer.Argument(default=None),  # noqa
    config_path: ConfigOption = default_config,
) -> None:
    console = Console()
    error_console = Console(stderr=True)
    ctx = gather_context(config_path)

    def print_environment(environment: Environment) -> None:
        console.print(f"{environment.config.id}")
        console.print(f"  config.ecosystem: {environment.config.ecosystem}")
        console.print(f"  path: {environment._path}")
        console.print(f"  lock-files-path: {environment.lock_files_path}")

        state = environment.state
        if isinstance(state, UninitializedState):
            console.print("  state: uninitialized")
        elif isinstance(state, InitialState):
            console.print("  state: initial")
            console.print(f"  state.stage: {state.stage.value}")
            console.print(f"  state.ecosystem: {state.ecosystem}")
        elif isinstance(state, SyncedState):
            console.print("  state: synced")
            console.print(f"  state.stage: {state.stage.value}")
            console.print(f"  state.ecosystem: {state.ecosystem}")
            console.print(f"  state.checksum: {state.checksum!r}")

        else:
            assert_never(state)

    if selected_environment is None:
        for environment in ctx.environments.values():
            print_environment(environment)
        return

    try:
        environment = ctx.environments[EnvironmentId(selected_environment)]
    except KeyError:
        error_console.print("No such environment")
        raise typer.Exit(1) from None

    print_environment(environment)


@cli.command()
@asyncio_entrypoint
async def select(
    selected_hook: str = typer.Argument(),
    config_path: ConfigOption = default_config,
    select: Selector = typer.Option(default="diff"),
) -> None:
    """Show file selection for a given hook."""
    error_console = Console(stderr=True)
    console = Console()
    ctx = gather_context(config_path)

    try:
        hook = next(hook for hook in ctx.config.hooks if hook.id == selected_hook)
    except StopIteration:
        error_console.print("No such hook.")
        raise typer.Exit(1) from None

    if not hook.parameterize:
        error_console.print(
            "Hook is not parameterized, no target files are passed to it."
        )
        return

    targets = await get_targets(ctx.config, select)
    target_files = filter_hook_targets(hook, targets)
    for file in target_files:
        console.print(file)


template = """\
#!/usr/bin/env bash
set -euo pipefail
goose run '--config={config_path}'
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


def version_callback(print_version: bool) -> None:
    if not print_version:
        return
    print(f"goose version {__version__}")
    raise typer.Exit()


@cli.callback()
def main(
    version: bool = typer.Option(
        None,
        "--version",
        callback=version_callback,
        is_eager=True,
        help="Print version information.",
    ),
) -> None:
    pass


if __name__ == "__main__":
    cli()
