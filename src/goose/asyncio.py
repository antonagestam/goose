import asyncio
import functools
from typing import Callable, ParamSpec, TypeVar, Coroutine

P = ParamSpec("P")
R = TypeVar("R")


def asyncio_entrypoint(
    fn: Callable[P, Coroutine[None, None, R]],
) -> Callable[P, R]:
    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        return asyncio.run(fn(*args, **kwargs))

    return wrapper
