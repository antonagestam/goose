import asyncio
import math
import os
from collections.abc import Set
from dataclasses import dataclass
from pathlib import Path
from itertools import batched, chain
from typing import Iterable, Collection

from .config import HookConfig


def process_distribute(
    hook: HookConfig,
    target_files: Collection[Path],
) -> tuple[tuple[Path, ...], ...]:
    if not target_files:
        return ((),)
    process_count = os.cpu_count()
    if not hook.parameterize or process_count == 1:
        return (tuple(target_files),)
    num_batches = math.ceil(len(target_files) / process_count)
    return tuple(batched(target_files, num_batches))


def can_spawn_hook(
    candidate: HookConfig,
    tasks_running: tuple[HookConfig, ...],
) -> bool:
    """
    If running tasks have a disjoint file-set
    """
    ...


@dataclass(frozen=True, slots=True, kw_only=True)
class RunningHook:
    config: HookConfig
    task: asyncio.Task[None]
    targets: Set[Path]


def all_targets(
    running_hooks: Iterable[RunningHook],
) -> frozenset[Path]:
    return frozenset(chain(*(running_hook.targets for running_hook in running_hooks)))
