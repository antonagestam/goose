import asyncio
import functools
from collections.abc import Callable
from collections.abc import Coroutine


def asyncio_entrypoint[R, **P](
    fn: Callable[P, Coroutine[None, None, R]],
) -> Callable[P, R]:
    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        return asyncio.run(fn(*args, **kwargs))

    return wrapper
