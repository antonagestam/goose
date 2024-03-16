from pathlib import Path
from re import Pattern
from typing import Iterable


def path_matches_patterns(
    path: Path,
    patterns: Iterable[Pattern],
) -> bool:
    return any(pattern.search(str(path)) is not None for pattern in patterns)
