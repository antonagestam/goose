from __future__ import annotations

from collections.abc import Iterable
from collections.abc import Mapping
from pathlib import Path
from re import Pattern
from typing import Annotated
from typing import Literal
from typing import NewType
from typing import Self
from typing import final

import yaml
from pydantic import BeforeValidator
from pydantic import model_validator
from pydantic_core.core_schema import ValidationInfo

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


def mapping_as_items(
    value: object,
    info: ValidationInfo,
) -> Iterable[tuple]:
    if not isinstance(value, Mapping):
        raise ValueError(f"Field {info.field_name} must be a mapping")
    return value.items()


type ItemTuple[K, V] = Annotated[
    tuple[tuple[K, V], ...],
    BeforeValidator(mapping_as_items),
]


@final
class HookConfig(BaseModel):
    id: str
    environment: EnvironmentId
    command: str
    args: tuple[str, ...] = ()
    env_vars: ItemTuple[str, str] = ()
    parameterize: bool = True
    types: frozenset[str] = frozenset()
    exclude: tuple[Pattern, ...] = ()
    read_only: bool = False


@final
class Config(BaseModel):
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
    def validate_hook_ids_unique(self) -> Self:
        if len({hook.id for hook in self.hooks}) != len(self.hooks):
            raise ValueError("Hook ids must be unique")
        return self

    @model_validator(mode="after")  # type: ignore[misc]
    def validate_environment_ids_unique(self) -> Self:
        if len({env.id for env in self.environments}) != len(self.environments):
            raise ValueError("Environment ids must be unique")
        return self


def load_config(path: Path) -> Config:
    with path.open("rb") as fd:
        loaded = yaml.safe_load(fd)
    return Config.model_validate(loaded)
