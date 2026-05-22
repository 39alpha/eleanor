import warnings
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from eleanor.executor.interface import AbstractExecutor


def _normalize_num_workers(num_workers: int | None) -> int | None:
    if num_workers is None:
        return None
    if num_workers <= 0:
        return 1
    return num_workers


def build_serial(*, num_workers: int | None = None, **kwargs: object) -> AbstractExecutor:
    if num_workers is not None:
        warnings.warn(
            "num_workers is ignored for serial executor",
            RuntimeWarning,
            stacklevel=3,
        )
    if kwargs:
        warnings.warn(
            f'built-in executor "serial" does not accept keyword arguments; ignoring: {list(kwargs)}',
            RuntimeWarning,
            stacklevel=3,
        )
    from eleanor.executor.serial import SerialExecutor

    return SerialExecutor()


def build_multiprocessing(*, num_workers: int | None = None, **kwargs: object) -> AbstractExecutor:
    if kwargs:
        warnings.warn(
            f'built-in executor "multiprocessing" does not accept keyword arguments; ignoring: {list(kwargs)}',
            RuntimeWarning,
            stacklevel=3,
        )

    from eleanor.executor.multiprocessing import MultiprocessingExecutor

    return MultiprocessingExecutor(num_workers=_normalize_num_workers(num_workers))


build_serial.__eleanor_api_version__ = 1  # pyright: ignore[reportFunctionMemberAccess]
build_multiprocessing.__eleanor_api_version__ = 1  # pyright: ignore[reportFunctionMemberAccess]

__all__ = [
    "build_multiprocessing",
    "build_serial",
]
