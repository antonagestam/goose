from __future__ import annotations

import pydantic


class BaseModel(
    pydantic.BaseModel,
    frozen=True,
    extra="forbid",
): ...
