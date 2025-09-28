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

type Language = Literal["python", "node", "system"]


@final
class VersionedEcosystemConfig(BaseModel):
    language: Language
    version: str | None = None


type EcosystemConfig = VersionedEcosystemConfig | Language


def get_ecosystem_version(
    config: VersionedEcosystemConfig | Language,
) -> str | None:
    return config.version if isinstance(config, VersionedEcosystemConfig) else None


def get_ecosystem_language(
    config: VersionedEcosystemConfig | Language,
) -> Language:
    return config.language if isinstance(config, VersionedEcosystemConfig) else config


EnvironmentId = NewType("EnvironmentId", str)


@final
class EnvironmentConfig(BaseModel):
    id: EnvironmentId
    ecosystem: EcosystemConfig | Language
    dependencies: tuple[str, ...]

    @model_validator(mode="before")
    @classmethod
    def infer_id(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        if "id" in data:
            return data
        ecosystem = data.get("ecosystem")
        if isinstance(ecosystem, str):
            data["id"] = ecosystem
        elif isinstance(ecosystem, Mapping) and isinstance(
            (language := ecosystem.get("language")), str
        ):
            data["id"] = language
        return data


def mapping_as_items(
    value: object,
    info: ValidationInfo,
) -> Iterable[tuple]:
    if not isinstance(value, Mapping):
        raise ValueError(f"Field {info.field_name!r} must be a mapping")
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
    limit: tuple[Pattern, ...] = ()
    exclude: tuple[Pattern, ...] = ()
    read_only: bool = False


@final
class Config(BaseModel):
    environments: tuple[EnvironmentConfig, ...]
    hooks: tuple[HookConfig, ...]
    limit: tuple[Pattern, ...] = ()
    exclude: tuple[Pattern, ...] = ()

    @model_validator(mode="after")  # type: ignore[misc]
    def validate_hook_environments_configured(self) -> Self:
        environments = {env.id for env in self.environments}
        for hook in self.hooks:
            if hook.environment not in environments:
                raise ValueError(
                    f"unknown hook environment: {hook.environment!r}. This must refer "
                    f"to an environment id defined in top-level environments."
                )
        return self

    @model_validator(mode="after")  # type: ignore[misc]
    def validate_hook_ids_unique(self) -> Self:
        if len({hook.id for hook in self.hooks}) != len(self.hooks):
            raise ValueError("hook ids must be unique.")
        return self

    @model_validator(mode="after")  # type: ignore[misc]
    def validate_environment_ids_unique(self) -> Self:
        if len({env.id for env in self.environments}) != len(self.environments):
            raise ValueError("environment ids must be unique")
        return self


def load_config(path: Path) -> Config:
    with path.open("rb") as fd:
        loaded = yaml.safe_load(fd)
    return Config.model_validate(loaded)
