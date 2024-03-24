import asyncio
import os
from collections.abc import Sequence, AsyncIterator
from itertools import chain
from typing import Final, TypeAlias, Mapping, assert_never

from .backend.base import RunResult
from .config import HookConfig
from .context import Context
from .executable_unit import ExecutableUnit
from .parallel import hook_as_executable_units
from .targets import Target


SchedulerState: TypeAlias = Mapping[
    HookConfig, Mapping[ExecutableUnit, RunResult | asyncio.Task[RunResult] | None]
]


class Scheduler:
    def __init__(
        self,
        context: Context,
        targets: Sequence[Target],
        selected_hook: str | None = None,
    ) -> None:
        self._context: Final = context
        self._max_running: Final = os.cpu_count() or 2
        self._units: Final = {
            hook: tuple(hook_as_executable_units(hook, targets))
            for hook in context.config.hooks
            if selected_hook is None or hook.id == selected_hook
        }

        if not self._units:
            if selected_hook is None:
                raise RuntimeError("No hooks configured")
            else:
                raise RuntimeError(f"Unknown hook id: {selected_hook}")

        self._remaining_units: Final[list[ExecutableUnit]] = list(
            chain(*self._units.values())
        )
        self._running_units: Final[dict[ExecutableUnit, asyncio.Task[RunResult]]] = {}
        self._results: Final[dict[ExecutableUnit, RunResult]] = {}

    def _schedule_unit(self, unit: ExecutableUnit) -> None:
        self._remaining_units.remove(unit)
        environment = self._context.environments[unit.hook.environment]
        self._running_units[unit] = environment.run(unit)

    def _schedule_max(self) -> None:
        for unit in tuple(self._remaining_units):
            # If we're at capacity, don't schedule more.
            if len(self._running_units) >= self._max_running:
                return

            # If no other task running, start.
            if not self._running_units:
                self._schedule_unit(unit)
                continue

            # If running tasks have disjoint set of files vs current, start.
            running_file_set = frozenset(
                chain(*(unit.targets for unit in self._running_units.keys()))
            )
            if not unit.targets & running_file_set:
                self._schedule_unit(unit)
                continue

            # If running tasks overlap with current, but neither mutates, start.
            if unit.hook.read_only and all(
                other_unit.hook.read_only for other_unit in self._running_units.keys()
            ):
                self._schedule_unit(unit)
                continue

    def _prune_running(self) -> None:
        # Move completed tasks from running to results.
        for unit, task in self._running_units.items():
            if not task.done():
                continue
            self._results[unit] = task.result()
        for unit in self._results.keys():
            try:
                del self._running_units[unit]
            except KeyError:
                pass

    async def _wait_next(self) -> None:
        await asyncio.wait(
            self._running_units.values(),
            return_when=asyncio.FIRST_COMPLETED,
        )
        # Remove completed tasks from running, and populate results.
        self._prune_running()

    async def until_complete(self) -> AsyncIterator[None]:
        """
        Iteratively try scheduling as many tasks as possible, until all are
        scheduled. Once all tasks are running, await completion of every task.
        Whenever a task is scheduled, or completed, yield.
        """
        while self._remaining_units:
            # Do a single loop over remaining tasks, and schedule as many as
            # possible.
            self._schedule_max()

            if not self._remaining_units:
                break

            # Await next finished task.
            await self._wait_next()
            yield

        while self._running_units:
            await self._wait_next()
            yield

    def _unit_state(
        self,
        unit: ExecutableUnit,
    ) -> RunResult | asyncio.Task[RunResult] | None:
        if (result := self._results.get(unit)) is not None:
            return result
        return self._running_units.get(unit)

    def state(self) -> SchedulerState:
        return {
            hook: {unit: self._unit_state(unit) for unit in units}
            for hook, units in self._units.items()
        }


def format_unit_state(
    state: RunResult | asyncio.Task[RunResult] | None,
) -> str:
    match state:
        case None:
            return "[W]"
        case asyncio.Task():
            return "[R]"
        case RunResult.ok:
            return "[D]"
        case RunResult.error:
            return "[E]"
        case no_match:
            assert_never(no_match)


def exit_code(state: SchedulerState) -> int:
    for units in state.values():
        for unit_state in units.values():
            if unit_state is RunResult.error:
                return 1
    return 0
