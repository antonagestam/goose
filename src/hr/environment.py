import enum
import sys
from pathlib import Path
from typing import final, Final, assert_never, Sequence, Mapping

from pydantic import RootModel

from ._utils.pydantic import BaseModel
from .backend.index import load_backend
from .config import EnvironmentConfig, Config, HookConfig, EnvironmentId
from .filter import path_matches_patterns
from .manifest import check_lock_files, LockFileState, read_manifest
from .targets import Target


class InitialStage(enum.Enum):
    new = "new"
    bootstrapped = "bootstrapped"
    frozen = "frozen"


class SyncedStage(enum.Enum):
    synced = "synced"


class SyncedState(BaseModel):
    stage: SyncedStage
    checksum: str


class InitialState(BaseModel):
    stage: InitialStage


_PersistedState = RootModel[InitialState | SyncedState]


def read_state(env_dir: Path) -> InitialState | SyncedState:
    state_file = env_dir / "hr-state.json"
    if not state_file.exists():
        return InitialState(stage=InitialStage.new)
    return _PersistedState.model_validate_json(state_file.read_bytes()).root


def write_state(env_dir: Path, state: InitialState | SyncedState) -> None:
    state_file = env_dir / "hr-state.json"
    state_file.write_text(state.model_dump_json())


@final
class Environment:
    def __init__(
        self,
        config: EnvironmentConfig,
        path: Path,
        lock_files_path: Path,
        discovered_state: InitialState | SyncedState,
    ) -> None:
        self.config: Final = config
        self._backend: Final = load_backend(config.ecosystem)
        self._path: Final = path
        self.lock_files_path: Final = lock_files_path / config.id
        # This is read initially from file-system, so we don't entirely trust
        # it. Each stage does some additional steps to verify we are in sync.
        self.state = discovered_state

    def check_should_bootstrap(self) -> bool:
        if self.state.stage is InitialStage.new:
            return True
        if not self._path.exists():
            print("State mismatch: environment does not exist")
            return False
        return False

    def check_should_freeze(self) -> bool:
        if (
            self.state.stage is InitialStage.new
            or self.state.stage is InitialStage.bootstrapped
        ):
            return True

        # Check if current lock files are up-to-date with dependencies
        # configured for the environment.
        match check_lock_files(
            lock_files_path=self.lock_files_path,
            state_checksum=None,
            config=self.config,
        ):
            case (
                LockFileState.missing_lock_file
                | LockFileState.manifest_lock_file_mismatch
                | LockFileState.config_manifest_mismatch
            ):
                return True
            case (
                LockFileState.matching
                # Mismatch between state and manifest needs _sync_ needs to run, but
                # does not indicate lock files are out of sync with configured
                # dependencies. So no need to run freeze again.
                | LockFileState.state_manifest_mismatch
            ):
                return False
            case no_match:
                assert_never(no_match)

    def check_should_sync(self) -> bool:
        if not isinstance(self.state, SyncedState):
            return True

        match check_lock_files(
            lock_files_path=self.lock_files_path,
            state_checksum=self.state.checksum,
            config=self.config,
        ):
            case LockFileState.matching:
                return False
            case LockFileState.missing_lock_file:
                print(
                    f"[{self.config.id}] Expected lock file is missing.",
                    file=sys.stderr,
                )
                return True
            case LockFileState.state_manifest_mismatch:
                print(
                    f"[{self.config.id}] Environment state does not match manifest.",
                    file=sys.stderr,
                )
                return True
            case LockFileState.manifest_lock_file_mismatch:
                raise RuntimeError(
                    "Manifest does not match lock file, needs freezing. "
                    "This should not normally occur, as freezing is always "
                    "checked before syncing."
                )
            case no_match:
                assert_never(no_match)

    async def bootstrap(self) -> None:
        await self._backend.bootstrap(
            env_path=self._path,
            config=self.config,
        )
        self.state = InitialState(stage=InitialStage.bootstrapped)
        write_state(self._path, self.state)

    async def freeze(self) -> None:
        await self._backend.freeze(
            env_path=self._path,
            config=self.config,
            lock_files_path=self.lock_files_path,
        )
        self.state = InitialState(stage=InitialStage.frozen)
        write_state(self._path, self.state)

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
        )
        write_state(self._path, self.state)

    async def run(
        self,
        hook: HookConfig,
        targets: Sequence[Target],
    ) -> None:
        # Send empty sequence of files for non-parameterized hooks.
        if not hook.parameterize:
            target_files = ()
        # Skip parameterized hooks when target file sequence is empty.
        elif not targets:
            print("No target files")
            return
        else:
            target_files = (
                target.path
                for target in targets
                if target.tags & hook.types
                if not path_matches_patterns(target.path, hook.exclude)
            )

        await self._backend.run(
            env_path=self._path,
            config=self.config,
            hook=hook,
            target_files=target_files,
        )


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

    if environment.check_should_bootstrap():
        print(f"{log_prefix}Bootstrapping environment ...", file=sys.stderr)
        await environment.bootstrap()
        print(f"{log_prefix}Bootstrapping done.", file=sys.stderr)
    else:
        print(
            f"{log_prefix}Found previously bootstrapped environment.",
            file=sys.stderr,
        )

    if upgrade or environment.check_should_freeze():
        print(f"{log_prefix}Freezing dependencies ...", file=sys.stderr)
        await environment.freeze()
        print(f"{log_prefix}Freezing done.")
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
