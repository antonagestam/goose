import asyncio
from asyncio import StreamReader
from collections.abc import AsyncGenerator
from contextlib import chdir
from pathlib import Path

import pytest

from goose.targets import Selector
from goose.targets import _git_file_list
from goose.targets import _nil_split_stream
from goose.targets import _stream_paths


async def as_tuple[T](source: AsyncGenerator[T]) -> tuple[T, ...]:
    parts = []
    async for part in source:
        parts.append(part)
    return tuple(parts)


@pytest.mark.parametrize(
    ("input_bytes", "expected_chunks"),
    (
        (b"", ()),
        (b"foo", ()),
        (b"hello\n", (b"hello",)),
        (b"foo\00bar\n", (b"foo", b"bar")),
        (b"foo\00 bar\00baz \n", (b"foo", b"bar", b"baz")),
        (b"foo\nbar\n", (b"foo", b"bar")),
    ),
)
async def test_nil_split_stream(
    input_bytes: bytes,
    expected_chunks: tuple[bytes, ...],
) -> None:
    stream_reader = StreamReader()
    stream_reader.feed_data(input_bytes)
    stream_reader.feed_eof()
    chunks = await as_tuple(_nil_split_stream(stream_reader))
    assert chunks == expected_chunks


async def test_stream_paths() -> None:
    async def gen() -> AsyncGenerator[bytes]:
        yield b"a"
        yield b"b/c"
        yield b"/d"

    paths = await as_tuple(_stream_paths(gen()))
    assert paths == (
        Path("a"),
        Path("b/c"),
        Path("/d"),
    )


@pytest.fixture
async def git_repository(tmp_path: Path) -> AsyncGenerator[Path]:
    with chdir(tmp_path):
        # Initiate repository, configure name and email.
        create_repository = await asyncio.create_subprocess_exec("git", "init")
        await create_repository.wait()
        configure_email = await asyncio.create_subprocess_exec(
            "git",
            "config",
            "user.email",
            "goose@example.test",
        )
        await configure_email.wait()
        configure_name = await asyncio.create_subprocess_exec(
            "git",
            "config",
            "user.name",
            "Goosin Around",
        )
        await configure_name.wait()

        (checked_in := tmp_path / "checked-in.txt").write_text("foo")
        (staged := tmp_path / "staged.txt").write_text("bar")
        (tmp_path / "untracked.txt").write_text("baz")
        (deleted_staged := tmp_path / "deleted-staged.txt").write_text("lorem")
        (deleted_worktree := tmp_path / "deleted-worktree.txt").write_text("ipsum")

        add_file = await asyncio.create_subprocess_exec(
            "git",
            "add",
            str(checked_in),
            str(deleted_staged),
            str(deleted_worktree),
        )
        await add_file.wait()

        commit = await asyncio.create_subprocess_exec("git", "commit", "-minitial")
        await commit.wait()

        deleted_staged.unlink()
        deleted_worktree.unlink()
        rm_file = await asyncio.create_subprocess_exec("git", "rm", str(deleted_staged))
        await rm_file.wait()

        add_file = await asyncio.create_subprocess_exec("git", "add", str(staged))
        await add_file.wait()

        yield tmp_path


class TestGitFileList:
    async def test_listing_all_includes_commited_and_staged(
        self,
        git_repository: Path,
    ) -> None:
        result = await as_tuple(_git_file_list(Selector.all))
        assert result == (
            Path("checked-in.txt"),
            Path("staged.txt"),
        )

    async def test_listing_diff_includes_only_staged(
        self,
        git_repository: Path,
    ) -> None:
        result = await as_tuple(_git_file_list(Selector.diff))
        assert result == (Path("staged.txt"),)
