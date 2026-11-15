from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest

from goose.backend.node.backend import _get_highest_matching_version


class TestGetHighestMatchingVersion:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("configured_version", "output_data", "expected_version"),
        (
            (
                "20",
                "18.16.0\n20.10.0\t20.3.0\n19.0.0\n",
                "20.10.0",
            ),
            (
                "20",
                "18.16.0\n20.10.0\t20.3.0\n19.0.0\n21.3.2\n",
                "20.10.0",
            ),
            (
                "21.0.0-alpha",
                "21.0.0-alpha.1\n21.0.0-alpha.2\n21.0.0-beta.1\n",
                "21.0.0-alpha.2",
            ),
            # Don't implicitly resolve to pre-release version.
            (
                None,
                "18.16.0\n20.10.0\t20.3.0\n19.0.0\n21.0.0-alpha.1\n",
                "20.10.0",
            ),
        ),
    )
    async def test_returns_highest_matching_version(
        self,
        configured_version: str | None,
        output_data: str,
        expected_version: str,
    ) -> None:
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.stderr = AsyncMock()

        async def mock_stream_out(*args, **kwargs) -> None:
            buffer = args[2]
            buffer.write(output_data)

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_process),
            patch(
                "goose.backend.node.backend.stream_out",
                side_effect=mock_stream_out,
            ),
        ):
            version = await _get_highest_matching_version(configured_version)
            assert version == expected_version

    @pytest.mark.asyncio
    async def test_raises_runtime_error_on_process_failure(self) -> None:
        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.stderr = AsyncMock()

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_process),
            patch("goose.backend.node.backend.stream_out", AsyncMock()),
            pytest.raises(RuntimeError, match="Failed listing available node versions"),
        ):
            await _get_highest_matching_version(None)

    @pytest.mark.asyncio
    async def test_raises_runtime_error_when_no_match_found(self) -> None:
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.stderr = AsyncMock()

        async def mock_stream_out(*args, **kwargs) -> None:
            buffer = args[2]
            buffer.write("18.16.0\n19.0.0\n")

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_process),
            patch("goose.backend.node.backend.stream_out", side_effect=mock_stream_out),
            pytest.raises(
                RuntimeError, match="Found no available node versions matching"
            ),
        ):
            await _get_highest_matching_version("21")
