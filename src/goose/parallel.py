import math
import os
import sys
from collections.abc import Sequence
from itertools import batched
from typing import Iterator

from .config import HookConfig
from .executable_unit import ExecutableUnit
from .targets import filter_hook_targets, Target


def hook_as_executable_units(
    hook: HookConfig,
    targets: Sequence[Target],
) -> Iterator[ExecutableUnit]:
    target_files = filter_hook_targets(hook, targets)

    # Skip parameterized hooks when resulting target file sequence is empty.
    if hook.parameterize and not target_files:
        print(f"[{hook.id}] Skipped.", file=sys.stderr)
        return

    # Hook is not parameterized, yield single unit with empty file set.
    if not target_files:
        yield ExecutableUnit(hook=hook)
        return

    # fixme: remove
    assert hook.parameterize

    # Distribute target files over one executable unit per core.
    process_count = os.cpu_count() or 1
    batch_size = math.ceil(len(target_files) / process_count)
    for file_batch in batched(target_files, batch_size):
        yield ExecutableUnit(hook=hook, targets=frozenset(file_batch))
