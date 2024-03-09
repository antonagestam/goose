import hashlib
from functools import total_ordering
from pathlib import Path
from typing import final, Self, Iterable

from pydantic import field_validator
from ._utils.pydantic import BaseModel


@final
@total_ordering
class LockFile(BaseModel):
    path: str
    checksum: str

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, LockFile):
            return False
        return self.filename == other.filename

    def __lt__(self, other: Self) -> bool:
        return self.filename < other.filename


class LockManifest(BaseModel):
    source_dependencies: tuple[str, ...]
    lock_files: tuple[LockFile, ...]

    @field_validator("source_dependencies", "lock_files")
    @classmethod
    def validate_sorted(cls, v: tuple[object, ...]) -> None:
        if sorted(v) != list(v):
            raise ValueError("must be sorted")
        return v

    @field_validator("source_dependencies", "lock_files")
    @classmethod
    def validate_unique(cls, v: tuple[object, ...]) -> None:
        if len(set(v)) != len(v):
            raise ValueError("must be unique")
        return v

    @field_validator("source_dependencies", "lock_files")
    @classmethod
    def validate_non_empty(cls, v: tuple[object, ...]) -> None:
        if len(v) == 0:
            raise ValueError("must not be empty")
        return v


def _get_checksum(path: Path) -> str:
    checksum = hashlib.sha256(usedforsecurity=True)
    with path.open("rb") as fd:
        for line in fd.readlines():
            checksum.update(line)
    return f"sha256:{checksum.hexdigest()}"


def _build_lock_file(lock_files_path: Path, path: Path) -> LockFile:
    return LockFile(
        path=str(path.relative_to(lock_files_path)),
        checksum=_get_checksum(path),
    )


def build_manifest(
    source_dependencies: Iterable[str],
    lock_files: Iterable[Path],
    lock_files_path: Path,
) -> LockManifest:
    return LockManifest(
        source_dependencies=tuple(sorted(source_dependencies)),
        lock_files=tuple(
            _build_lock_file(lock_files_path, path)
            for path in lock_files
        )
    )
