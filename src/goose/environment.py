import asyncio
import enum
import os
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Final
from typing import assert_never
from typing import final

from pydantic import RootModel

from goose.git.status import get_git_status

from ._utils.pydantic import BaseModel
from .backend.base import RunResult
from .backend.index import load_backend
from .config import Config
from .config import EcosystemConfig
from .config import EnvironmentConfig
from .config import EnvironmentId
from .executable_unit import ExecutableUnit
from .manifest import LockFileState
from .manifest import check_lock_files
from .manifest import read_manifest


class NeedsFreeze(Exception): ...


class InitialStage(enum.Enum):
    bootstrapped = "bootstrapped"
    frozen = "frozen"


class SyncedStage(enum.Enum):
    synced = "synced"


class SyncedState(BaseModel):
    stage: SyncedStage
    checksum: str
    ecosystem: EcosystemConfig


class InitialState(BaseModel):
    stage: InitialStage
    ecosystem: EcosystemConfig


class UninitializedState: ...


type State = SyncedState | InitialState | UninitializedState

_PersistedState = RootModel[SyncedState | InitialState]


def read_state(env_dir: Path) -> State:
    state_file = env_dir / "goose-state.json"
    if not state_file.exists():
        return UninitializedState()
    return _PersistedState.model_validate_json(state_file.read_bytes()).root


def write_state(env_dir: Path, state: SyncedState | InitialState) -> None:
    state_file = env_dir / "goose-state.json"
    state_file.write_text(state.model_dump_json())


@final
class Environment:
    def __init__(
        self,
        config: EnvironmentConfig,
        path: Path,
        lock_files_path: Path,
        discovered_state: State,
    ) -> None:
        self.config: Final = config
        self._backend: Final = load_backend(config.ecosystem)
        self._path: Final = path
        self.lock_files_path: Final = lock_files_path / config.id
        # This is read initially from file-system, so we don't entirely trust
        # it. Each stage does some additional steps to verify we are in sync.
        self.state = discovered_state

    def __repr__(self) -> str:
        return f"Environment(id={self.config.id}, ecosystem={self._backend.ecosystem})"

    def check_should_teardown(self) -> bool:
        if isinstance(self.state, UninitializedState):
            return False
        return self.config.ecosystem != self.state.ecosystem

    def check_should_bootstrap(self) -> bool:
        if isinstance(self.state, UninitializedState):
            return True
        if not self._path.exists():
            print("State mismatch: environment does not exist")
            return False
        return False

    def check_should_freeze(self) -> bool:
        # Check if current lock files are up-to-date with dependencies
        # configured for the environment.
        state = check_lock_files(
            lock_files_path=self.lock_files_path,
            state_checksum=None,
            config=self.config,
        )

        if (
            state is LockFileState.missing_lock_file
            or state is LockFileState.manifest_lock_file_mismatch
            or state is LockFileState.config_manifest_mismatch
        ):
            return True
        elif (
            state is LockFileState.matching
            # Mismatch between state and manifest needs _sync_ needs to run, but
            # does not indicate lock files are out of sync with configured
            # dependencies. So no need to run freeze again.
            or state is LockFileState.state_manifest_mismatch
        ):
            return False
        else:
            assert_never(state)

    def check_should_sync(self) -> bool:
        if not isinstance(self.state, SyncedState):
            return True

        state = check_lock_files(
            lock_files_path=self.lock_files_path,
            state_checksum=self.state.checksum,
            config=self.config,
        )

        if state is LockFileState.matching:
            return False
        elif state is LockFileState.missing_lock_file:
            print(
                f"[{self.config.id}] Expected lock file is missing.",
                file=sys.stderr,
            )
            return True
        elif state is LockFileState.state_manifest_mismatch:
            print(
                f"[{self.config.id}] Environment state does not match manifest.",
                file=sys.stderr,
            )
            return True
        elif state is LockFileState.manifest_lock_file_mismatch:
            raise RuntimeError(
                "Manifest does not match lock file, needs freezing. "
                "This should not normally occur, as freezing is always "
                "checked before syncing."
            )
        elif state is LockFileState.config_manifest_mismatch:
            raise RuntimeError(
                "Manifest does not match configuration, needs freezing. "
                "This should not normally occur, as freezing is always "
                "checked before syncing."
            )
        else:
            assert_never(state)

    async def teardown(self) -> None:
        await asyncio.to_thread(shutil.rmtree, self._path)
        self.state = UninitializedState()

    async def bootstrap(self) -> None:
        await self._backend.bootstrap(
            env_path=self._path,
            config=self.config,
        )
        self.state = InitialState(
            stage=InitialStage.bootstrapped,
            ecosystem=self.config.ecosystem,
        )
        write_state(self._path, self.state)

    async def freeze(self) -> None:
        await self._backend.freeze(
            env_path=self._path,
            config=self.config,
            lock_files_path=self.lock_files_path,
        )
        self.state = InitialState(
            stage=InitialStage.frozen,
            ecosystem=self.config.ecosystem,
        )
        write_state(self._path, self.state)
        os.sync()

    async def sync(self) -> None:
        manifest = read_manifest(self.lock_files_path)
        await self._backend.sync(
            env_path=self._path,
            config=self.config,
            lock_files_path=self.lock_files_path,
        )
        self.state = SyncedState(
            stage=SyncedStage.synced,
            checksum=manifest.checksum,
            ecosystem=self.config.ecosystem,
        )
        write_state(self._path, self.state)

    async def run(self, unit: ExecutableUnit) -> RunResult:
        coroutine = self._backend.run(
            env_path=self._path,
            config=self.config,
            unit=unit,
        )

        # We don't track modifications for read-only hooks.
        if unit.hook.read_only:
            return await coroutine

        status_prior = await get_git_status(unit.targets)
        result = await coroutine
        if result is RunResult.error:
            return result
        status_post = await get_git_status(unit.targets)
        if status_prior != status_post:
            return RunResult.modified
        return result


def build_environments(
    config: Config,
    env_dir: Path,
    lock_files_path: Path,
) -> Mapping[EnvironmentId, Environment]:
    environments = {}
    for cfg in config.environments:
        path = env_dir / cfg.id
        environments[cfg.id] = Environment(
            config=cfg,
            path=path,
            lock_files_path=lock_files_path,
            discovered_state=read_state(path),
        )
    return environments


async def prepare_environment(
    environment: Environment,
    upgrade: bool = False,
) -> None:
    log_prefix = f"[{environment.config.id}] "

    if environment.check_should_teardown():
        print(
            f"{log_prefix}Environment needs rebuilding, tearing down ...",
            file=sys.stderr,
        )
        await environment.teardown()
        print(
            f"{log_prefix}Environment deleted.",
            file=sys.stderr,
        )

    if environment.check_should_bootstrap():
        print(f"{log_prefix}Bootstrapping environment ...", file=sys.stderr)
        await environment.bootstrap()
        print(f"{log_prefix}Bootstrapping done.", file=sys.stderr)
    else:
        print(
            f"{log_prefix}Found previously bootstrapped environment.",
            file=sys.stderr,
        )

    if upgrade:
        print(f"{log_prefix}Freezing dependencies ...", file=sys.stderr)
        await environment.freeze()
        print(f"{log_prefix}Freezing done.")
    elif environment.check_should_freeze():
        print(f"{log_prefix}Missing lock files.", file=sys.stderr)
        raise NeedsFreeze
    else:
        print(f"{log_prefix}Found existing lock files up-to-date.", file=sys.stderr)

    if environment.check_should_sync():
        print(f"{log_prefix}Syncing dependencies ...", file=sys.stderr)
        await environment.sync()
        print(f"{log_prefix}Syncing done.", file=sys.stderr)
    else:
        print(
            f"{log_prefix}Found dependencies up-to-date.",
            file=sys.stderr,
        )
