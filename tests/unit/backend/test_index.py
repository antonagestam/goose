import pytest

from goose.backend import node
from goose.backend import python
from goose.backend import system
from goose.backend.index import load_backend


class TestLoadBackend:
    @pytest.mark.parametrize(
        ("language", "expected"),
        (
            ("python", python.backend),
            ("node", node.backend),
            ("system", system.backend),
        ),
    )
    def test_can_load_backend(self, language: str, expected: object) -> None:
        assert load_backend(language) == expected

    def test_raises_key_error_for_unknown_language(self) -> None:
        with pytest.raises(KeyError):
            load_backend("foo")
