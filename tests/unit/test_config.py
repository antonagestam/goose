import textwrap
from pathlib import Path
from unittest import mock

import pytest
from pydantic import ValidationError
from pydantic_core import ErrorDetails

from goose.config import Config
from goose.config import EcosystemConfig
from goose.config import EnvironmentConfig
from goose.config import HookConfig
from goose.config import load_config
from goose.config import mapping_as_items


class TestMappingAsItems:
    def test_raises_value_error_for_non_mapping_value(self) -> None:
        info = mock.MagicMock(field_name="some-field")
        with pytest.raises(ValueError, match=r"^Field 'some-field' must be a mapping"):
            mapping_as_items(object(), info)

    def test_returns_iterable_of_key_value_tuples(self) -> None:
        info = mock.MagicMock(spec_set=True)
        value = {
            "foo": "bar",
            "bar": "baz",
        }
        assert tuple(mapping_as_items(value, info)) == (
            ("foo", "bar"),
            ("bar", "baz"),
        )


class TestConfigModel:
    def validate_and_get_error(self, data: object) -> ErrorDetails:
        with pytest.raises(ValidationError) as exc_info:
            Config.model_validate(data)
        [error] = exc_info.value.errors()
        return error

    def test_raises_value_error_for_unknown_environment(self) -> None:
        error = self.validate_and_get_error(
            {
                "environments": (),
                "hooks": [
                    {
                        "id": "some-hook",
                        "environment": "missing-env",
                        "command": "some-command",
                    },
                ],
            }
        )
        assert error["type"] == "value_error"
        assert error["loc"] == ()
        assert error["msg"] == (
            "Value error, unknown hook environment: 'missing-env'. This must refer to "
            "an environment id defined in top-level environments."
        )

    def test_raises_value_error_for_non_unique_hook_id(self) -> None:
        error = self.validate_and_get_error(
            {
                "environments": [
                    {
                        "id": "an-env",
                        "ecosystem": {
                            "language": "python",
                            "version": "3.13",
                        },
                        "dependencies": (),
                    }
                ],
                "hooks": [
                    {
                        "id": "some-hook",
                        "environment": "an-env",
                        "command": "some-command",
                    },
                    {
                        "id": "some-hook",
                        "environment": "an-env",
                        "command": "other-command",
                    },
                ],
            }
        )
        assert error["type"] == "value_error"
        assert error["loc"] == ()
        assert error["msg"] == "Value error, hook ids must be unique."

    def test_raises_value_error_for_non_unique_environment_id(self) -> None:
        error = self.validate_and_get_error(
            {
                "environments": [
                    {
                        "id": "an-env",
                        "ecosystem": {
                            "language": "python",
                            "version": "3.13",
                        },
                        "dependencies": (),
                    },
                    {
                        "id": "an-env",
                        "ecosystem": {
                            "language": "python",
                            "version": "3.13",
                        },
                        "dependencies": (),
                    },
                ],
                "hooks": [
                    {
                        "id": "some-hook",
                        "environment": "an-env",
                        "command": "some-command",
                    },
                ],
            }
        )
        assert error["type"] == "value_error"
        assert error["loc"] == ()
        assert error["msg"] == "Value error, environment ids must be unique"


class TestLoadConfig:
    def test_can_load_valid_config(self, tmp_path: Path) -> None:
        config_path = tmp_path / "goose.yaml"
        config_path.write_text(
            textwrap.dedent(
                """\
                environments:
                  - id: python
                    ecosystem:
                      language: python
                      version: "3.13"
                    dependencies:
                      - ruff
                  - id: node
                    ecosystem:
                      language: node
                      version: "23.0.0"
                    dependencies: [prettier]
                exclude:
                  - "^tests/"
                hooks:
                  - id: foo
                    environment: python
                    command: python
                    args: ["-c", 'print("hello")']
                    parameterize: false
                    read_only: true
                    env_vars:
                      ABC: "123"
                    types: [python]
                  - id: prettier
                    environment: node
                    command: prettier
                    types: [markdown]
                    exclude:
                      - "^src/"
                """
            )
        )
        config = load_config(config_path)
        assert config == Config(
            environments=(
                EnvironmentConfig(
                    id="python",
                    ecosystem=EcosystemConfig(
                        language="python",
                        version="3.13",
                    ),
                    dependencies=("ruff",),
                ),
                EnvironmentConfig(
                    id="node",
                    ecosystem=EcosystemConfig(
                        language="node",
                        version="23.0.0",
                    ),
                    dependencies=("prettier",),
                ),
            ),
            exclude=(r"^tests/",),
            hooks=(
                HookConfig(
                    id="foo",
                    environment="python",
                    command="python",
                    args=("-c", 'print("hello")'),
                    parameterize=False,
                    read_only=True,
                    env_vars={"ABC": "123"},
                    types=("python",),
                ),
                HookConfig(
                    id="prettier",
                    environment="node",
                    command="prettier",
                    types=("markdown",),
                    exclude=(r"^src/",),
                ),
            ),
        )
