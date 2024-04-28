from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .config import EnvironmentId
from .config import load_config
from .environment import Environment
from .environment import build_environments
from .paths import get_env_path


@dataclass(frozen=True, slots=True, kw_only=True)
class Context:
    config: Config
    lock_files_path: Path
    environments_path: Path
    environments: Mapping[EnvironmentId, Environment]


def gather_context(
    config_path: Path,
) -> Context:
    lock_files_path = Path("./.goose").resolve()
    lock_files_path.mkdir(exist_ok=True)
    config = load_config(config_path)
    environments_path = get_env_path()
    return Context(
        config=config,
        # fixme: should be configurable.
        lock_files_path=lock_files_path,
        environments_path=environments_path,
        environments=build_environments(config, environments_path, lock_files_path),
    )
