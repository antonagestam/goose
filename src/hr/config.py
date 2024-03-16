from __future__ import annotations

from re import Pattern
from typing import Literal, final, Self

from pathlib import Path
import yaml

from pydantic import model_validator
from ._utils.pydantic import BaseModel


@final
class EcosystemConfig(BaseModel):
    language: Literal["python", "node"]
    version: str


@final
class EnvironmentConfig(BaseModel):
    id: str
    ecosystem: EcosystemConfig
    dependencies: tuple[str, ...]


@final
class HookConfig(BaseModel):
    id: str
    environment: str
    command: str
    args: tuple[str, ...] = ()
    parameterize: bool = True
    types: frozenset[str] = frozenset()


@final
class Config(BaseModel):
    version: Literal[0]
    environments: tuple[EnvironmentConfig, ...]
    hooks: tuple[HookConfig, ...]
    exclude: tuple[Pattern, ...] = ()

    @model_validator(mode="after")
    def validate_hook_environments_configured(self) -> Self:
        environments = {env.id for env in self.environments}
        for hook in self.hooks:
            if hook.environment not in environments:
                raise ValueError(f"Unknown hook environment: {hook.environment!r}")
        return self


def load_config(path: Path) -> Config:
    with path.open("rb") as fd:
        loaded = yaml.safe_load(fd)
    return Config.parse_obj(loaded)