from __future__ import annotations
from typing import Literal, final, Self

from pathlib import Path
import yaml
import enum

from pydantic import model_validator
from ._utils.pydantic import BaseModel


class Parallelism(enum.Enum):
    none = "none"
    """
    Hook will be run without distribution to multiple processes, and without
    any other tasks running simultaneously.
    """
    distributed = "distributed"
    """
    Hook will not run simultaneously to other hooks, but will be distributed
    across multiple processes.
    """
    independent = "independent"
    """
    Hook will run simultaneously to other hooks, and distributed across multiple
    processes.
    """


@final
class LanguageConfig(BaseModel):
    id: Literal["python"]
    version: str


@final
class EnvironmentConfig(BaseModel):
    id: str
    language: LanguageConfig
    dependencies: tuple[str, ...]


@final
class HookConfig(BaseModel):
    id: str
    environment: str
    command: str
    parallelism: Parallelism = Parallelism.none


@final
class Config(BaseModel):
    version: Literal[0]
    environments: tuple[EnvironmentConfig, ...]
    hooks: tuple[HookConfig, ...]

    @model_validator(mode="after")
    def validate_hook_environments_configured(self) -> Self:
        environments = {env.id for env in self.environments}
        for hook in self.hooks:
            if hook.environment not in environments:
                raise ValueError(
                    f"Unknown hook environment: {hook.environment!r}")
        return self


def load_config(path: Path) -> Config:
    with path.open("rb") as fd:
        loaded = yaml.safe_load(fd)
    return Config.parse_obj(loaded)
