from pkgutil import extend_path
from typing import TYPE_CHECKING

__path__ = list(extend_path(__path__, __name__))
from eleanor.version import (
    __commit_id__,
    __version__,
    __version_tuple__,
    commit_id,
    version,
    version_tuple,
)

if TYPE_CHECKING:
    from eleanor.eleanor import Eleanor


def __getattr__(name: str) -> type[Eleanor]:
    if name == "Eleanor":
        from eleanor.eleanor import Eleanor

        return Eleanor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Eleanor",
    "__commit_id__",
    "__version__",
    "__version_tuple__",
    "commit_id",
    "version",
    "version_tuple",
]
