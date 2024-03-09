import math
import os
import sys
from collections.abc import Iterator
from collections.abc import Sequence
from itertools import batched

from .config import HookConfig
from .executable_unit import ExecutableUnit
from .targets import Target
from .targets import filter_hook_targets


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
        yield ExecutableUnit(id=0, hook=hook)
        return

    assert hook.parameterize

    # Distribute target files over one executable unit per core.
    process_count = os.cpu_count() or 2
    batch_size = math.ceil(len(target_files) / process_count)
    for unit_id, file_batch in enumerate(batched(target_files, batch_size)):
        yield ExecutableUnit(
            id=unit_id,
            hook=hook,
            targets=frozenset(file_batch),
        )
