import hashlib
import os
from pathlib import Path


def _get_cache_home() -> Path:
    if (xdg_home := os.environ.get("XDG_CACHE_HOME", None)) is not None:
        return Path(xdg_home).resolve()
    return Path.home().resolve() / ".cache"


def _get_base_envs_path() -> Path:
    return _get_cache_home() / "goose"


def _get_working_directory_hash() -> str:
    if (virtual_cwd := os.environ.get("GOOSE_AUGMENTED_CWD", None)) is not None:
        cwd = virtual_cwd.encode()
    else:
        cwd = bytes(Path(os.getcwd()).resolve())
    return hashlib.sha256(cwd).hexdigest()


def get_env_path() -> Path:
    base_path = _get_base_envs_path()
    cwd_hash = _get_working_directory_hash()
    env_path = base_path / cwd_hash
    env_path.mkdir(exist_ok=True, parents=True)
    return env_path
