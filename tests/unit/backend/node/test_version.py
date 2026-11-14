import pytest

from goose.backend.node._version import AlphaIdentifier
from goose.backend.node._version import NumericIdentifier
from goose.backend.node._version import Version
from goose.backend.node._version import parse_version


class TestParseVersion:
    @pytest.mark.parametrize(
        ("string", "expected"),
        (
            (
                "1.0.0",
                Version(1, 0, 0, ()),
            ),
            (
                "1.0.0-alpha.0.1",
                Version(
                    1,
                    0,
                    0,
                    (
                        AlphaIdentifier("alpha"),
                        NumericIdentifier(0),
                        NumericIdentifier(1),
                    ),
                ),
            ),
        ),
    )
    def test_returns_expected_version(
        self,
        string: str,
        expected: Version,
    ) -> None:
        assert parse_version(string) == expected

    @pytest.mark.parametrize(("string",), (("1",), ("1.0",), ("1.a.0",), ("1.0.foo",)))
    def test_raises_value_error_for_invalid_string(self, string: str) -> None:
        with pytest.raises(ValueError):
            parse_version(string)


@pytest.mark.parametrize(
    ("high", "low"),
    (
        ("0.0.1", "0.0.0"),
        ("0.1.0", "0.0.1"),
        ("1.0.0", "0.1.0"),
        ("0.0.10", "0.0.1"),
        ("0.10.0", "0.1.0"),
        ("10.0.0", "1.0.0"),
        ("1.0.0", "1.0.0-alpha"),
        ("1.0.0", "1.0.0-rc.1"),
        ("1.0.0-rc.1", "1.0.0-beta.11"),
        ("1.0.0-beta.11", "1.0.0-beta.2"),
        ("1.0.0-beta.2", "1.0.0-beta"),
        ("1.0.0-beta", "1.0.0-alpha.beta"),
        ("1.0.0-alpha.beta", "1.0.0-alpha.1"),
        ("1.0.0-alpha.1", "1.0.0-alpha"),
        ("1.0.0-alpha.1.0", "1.0.0-alpha.1"),
    ),
)
def test_version_is_less_than(high: str, low: str) -> None:
    assert parse_version(high) > parse_version(low)
    assert not parse_version(high) < parse_version(low)
    assert parse_version(low) < parse_version(high)
    assert not parse_version(low) > parse_version(high)


@pytest.mark.parametrize(
    ("a", "b"),
    (
        ("1.0.0", "1.0.0"),
        ("1.0.0-alpha.1.0", "1.0.0-alpha.1.0"),
    ),
)
def test_versions_are_equal(
    a: str,
    b: str,
) -> None:
    assert (parse_version(a) == parse_version(b)) is True
    assert (parse_version(b) == parse_version(a)) is True
    assert (parse_version(a) < parse_version(b)) is False
    assert (parse_version(b) < parse_version(a)) is False


@pytest.mark.parametrize(
    ("a", "b"),
    (
        ("1.0.0", "1.0.1"),
        ("1.0.0-alpha.1.0", "1.0.0-beta.1.0"),
    ),
)
def test_versions_are_not_equal(
    a: str,
    b: str,
) -> None:
    assert (parse_version(a) == parse_version(b)) is False
    assert (parse_version(b) == parse_version(a)) is False
