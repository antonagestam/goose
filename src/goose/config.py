from __future__ import annotations

from pathlib import Path
from re import Pattern
from typing import Literal
from typing import NewType
from typing import Self
from typing import final

import yaml
from pydantic import model_validator

from ._utils.pydantic import BaseModel


@final
class EcosystemConfig(BaseModel):
    language: Literal["python", "node"]
    version: str


EnvironmentId = NewType("EnvironmentId", str)


@final
class EnvironmentConfig(BaseModel):
    id: EnvironmentId
    ecosystem: EcosystemConfig
    dependencies: tuple[str, ...]


@final
class HookConfig(BaseModel):
    id: str
    environment: EnvironmentId
    command: str
    args: tuple[str, ...] = ()
    parameterize: bool = True
    types: frozenset[str] = frozenset()
    exclude: tuple[Pattern, ...] = ()
    read_only: bool = False
    after: tuple[str, ...] = ()


@final
class Config(BaseModel):
    version: Literal[0]
    environments: tuple[EnvironmentConfig, ...]
    hooks: tuple[HookConfig, ...]
    exclude: tuple[Pattern, ...] = ()

    @model_validator(mode="after")  # type: ignore[misc]
    def validate_hook_environments_configured(self) -> Self:
        environments = {env.id for env in self.environments}
        for hook in self.hooks:
            if hook.environment not in environments:
                raise ValueError(f"Unknown hook environment: {hook.environment!r}")
        return self

    @model_validator(mode="after")  # type: ignore[misc]
    def validate_hook_dependencies_exist(self) -> Self:
        configured_hooks = set[str]()
        configured_dependencies = set[str]()
        for hook in self.hooks:
            configured_hooks.add(hook.id)
            configured_dependencies.update(hook.after)
        if missing := (configured_dependencies - configured_hooks):
            raise ValueError(f"Unknown hooks configured as dependency: {missing}")
        return self


def load_config(path: Path) -> Config:
    with path.open("rb") as fd:
        loaded = yaml.safe_load(fd)
    return Config.model_validate(loaded)
