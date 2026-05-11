"""Built-in executor factories used by entry-point discovery."""

import warnings
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .interface import AbstractExecutor


def _normalize_num_workers(num_workers: int | None) -> int | None:
    """Clamp ``num_workers`` to ``>= 1``, preserving ``None`` as the default sentinel."""
    if num_workers is None:
        return None
    if num_workers <= 0:
        return 1
    return num_workers


def build_serial(num_workers: int | None) -> "AbstractExecutor":
    if num_workers is not None:
        warnings.warn(
            "num_workers is ignored for serial executor",
            RuntimeWarning,
            stacklevel=3,
        )
    from .serial import SerialExecutor

    return SerialExecutor()


def build_multiprocessing(num_workers: int | None) -> "AbstractExecutor":
    from .multiprocessing import MultiprocessingExecutor

    return MultiprocessingExecutor(num_workers=_normalize_num_workers(num_workers))


build_serial.__eleanor_api_version__ = 1  # pyright: ignore[reportFunctionMemberAccess]
build_multiprocessing.__eleanor_api_version__ = 1  # pyright: ignore[reportFunctionMemberAccess]
