import asyncio
import functools
from typing import Callable, Awaitable, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


def asyncio_entrypoint(fn: Callable[P, Awaitable[R]]) -> Callable[P, R]:
    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        return asyncio.run(fn(*args, **kwargs))

    return wrapper
