from typing import Final

from goose.backend.base import Backend

from .backend import bootstrap
from .backend import freeze
from .backend import run
from .backend import sync

backend: Final = Backend(
    ecosystem="node",
    bootstrap=bootstrap,
    freeze=freeze,
    sync=sync,
    run=run,
)
