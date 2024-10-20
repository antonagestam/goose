import enum
import hashlib
import sys
from collections.abc import Collection
from collections.abc import Iterable
from functools import total_ordering
from pathlib import Path
from typing import Self
from typing import final

from pydantic import ValidationInfo
from pydantic import field_validator

from ._utils.pydantic import BaseModel
from .config import EcosystemConfig
from .config import EnvironmentConfig


@final
@total_ordering
class LockFile(BaseModel):
    path: str
    checksum: str

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, LockFile):
            return False
        return self.path == other.path

    def __lt__(self, other: Self) -> bool:
        return self.path < other.path


class LockManifest(BaseModel):
    source_ecosystem: EcosystemConfig
    source_dependencies: tuple[str, ...]
    lock_files: tuple[LockFile, ...]
    checksum: str

    @field_validator("source_dependencies", "lock_files")
    @classmethod
    def validate_sorted[C: Collection](cls, v: C) -> C:
        if sorted(v) != list(v):
            raise ValueError("must be sorted")
        return v

    @field_validator("source_dependencies", "lock_files")
    @classmethod
    def validate_unique[C: Collection](cls, v: C) -> C:
        if len(set(v)) != len(v):
            raise ValueError("must be unique")
        return v

    @field_validator("source_dependencies", "lock_files")
    @classmethod
    def validate_non_empty[C: Collection](cls, v: C) -> C:
        if len(v) == 0:
            raise ValueError("must not be empty")
        return v

    @field_validator("checksum")
    @classmethod
    def validate_checksum_matches(cls, v: str, info: ValidationInfo) -> str:
        expected = _get_accumulated_checksum(info.data["lock_files"])
        if v != expected:
            raise ValueError(
                "checksum does not match accumulation of lock file checksums"
            )
        return v


def _get_accumulated_checksum(lock_files: Iterable[LockFile]) -> str:
    checksum = hashlib.sha256(usedforsecurity=True)
    for lock_file in lock_files:
        checksum.update(lock_file.checksum.encode())
    return f"sha256:{checksum.hexdigest()}"


def _get_checksum(path: Path) -> str:
    checksum = hashlib.sha256(usedforsecurity=True)
    with path.open("rb") as fd:
        for line in fd.readlines():
            checksum.update(line)
    return f"sha256:{checksum.hexdigest()}"


def read_lock_file(lock_files_path: Path, path: Path) -> LockFile:
    return LockFile(
        path=str(path.relative_to(lock_files_path)),
        checksum=_get_checksum(path),
    )


def build_manifest(
    source_ecosystem: EcosystemConfig,
    source_dependencies: Iterable[str],
    lock_files: Iterable[Path],
    lock_files_path: Path,
) -> LockManifest:
    lock_file_instances = tuple(
        sorted(read_lock_file(lock_files_path, path) for path in lock_files)
    )
    return LockManifest(
        source_ecosystem=source_ecosystem,
        source_dependencies=tuple(sorted(source_dependencies)),
        lock_files=lock_file_instances,
        checksum=_get_accumulated_checksum(lock_file_instances),
    )


def write_manifest(
    lock_files_path: Path,
    manifest: LockManifest,
) -> None:
    manifest_path = lock_files_path / "manifest.json"
    manifest_path.write_text(manifest.model_dump_json())
    print(f"Wrote manifest to {manifest_path}", file=sys.stderr)


def read_manifest(lock_files_path: Path) -> LockManifest:
    manifest_path = lock_files_path / "manifest.json"
    return LockManifest.model_validate_json(manifest_path.read_bytes())


class LockFileState(enum.Enum):
    missing_lock_file = enum.auto()
    state_manifest_mismatch = enum.auto()
    manifest_lock_file_mismatch = enum.auto()
    config_manifest_mismatch = enum.auto()
    matching = enum.auto()


def check_lock_files(
    lock_files_path: Path,
    state_checksum: str | None,
    config: EnvironmentConfig,
) -> LockFileState:
    try:
        manifest = read_manifest(lock_files_path)
    except FileNotFoundError:
        return LockFileState.config_manifest_mismatch

    if config.ecosystem != manifest.source_ecosystem:
        return LockFileState.config_manifest_mismatch

    if set(config.dependencies) ^ set(manifest.source_dependencies):
        return LockFileState.config_manifest_mismatch

    for persisted_lock_file in manifest.lock_files:
        path = lock_files_path / persisted_lock_file.path

        if not path.exists():
            return LockFileState.missing_lock_file

        actual_lock_file = read_lock_file(lock_files_path, path)

        if actual_lock_file != persisted_lock_file:
            return LockFileState.manifest_lock_file_mismatch

    if state_checksum != manifest.checksum:
        return LockFileState.state_manifest_mismatch

    return LockFileState.matching
