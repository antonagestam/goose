import hashlib
import os
from pathlib import Path


def _get_cache_home() -> Path:
    if (xdg_home := os.environ.get("XDG_CACHE_HOME", None)) is not None:
        return Path(xdg_home).resolve()
    return Path.home().resolve() / ".cache"


def _get_base_envs_path() -> Path:
    return _get_cache_home() / "goose"


def get_env_path() -> Path:
    base_path = _get_base_envs_path()
    cwd = Path(os.getcwd()).resolve()
    env_hash = hashlib.sha256(bytes(cwd))
    env_path = base_path / env_hash.hexdigest()
    env_path.mkdir(exist_ok=True, parents=True)
    return env_path
