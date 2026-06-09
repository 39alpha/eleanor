import datetime
import hashlib
import os
from collections.abc import Callable, Generator, Iterable, Sequence
from enum import StrEnum
from functools import reduce
from pathlib import Path
from typing import Protocol, TypeVar, cast

import numpy as np
from numpy.typing import NDArray

from eleanor.exceptions import EleanorException
from eleanor.typing import StrPath

MapInputT = TypeVar("MapInputT")
ReduceT = TypeVar("ReduceT")
ChunkInputT = TypeVar("ChunkInputT")


class HashLike(Protocol):
    def update(self, obj: bytes, /) -> object: ...

    def hexdigest(self) -> str: ...


# TODO: Use an enumeration for str_loc parameter
def find_files(match: str, location: StrPath = ".", str_loc: str = "suffix") -> tuple[list[Path], list[Path]]:
    """
    Find all files in folders downstream from 'location', with extension 'file_extension'

    :param match: characters to match in file names.
    :type match: str

    :param location: outermost parent directory beign searched.
    :type location: str

    :param str_loc: are the match characters at the beginning or end of the file?
    :type str_loc:  str ('prefix' or 'suffix')

    :return: list containing file names, list containing file paths
    :rtype: list, list
    """
    file_names: list[Path] = []
    file_paths: list[Path] = []
    for root, _dirs, files in Path(location).walk():
        for file in files:
            if (str_loc == "suffix" and file.endswith(match)) or (str_loc == "prefix" and file.startswith(match)):
                file_names.append(Path(file))
                file_paths.append(Path(root) / file)
    return file_names, file_paths


def ensure_directory(path: StrPath) -> None:
    """
    This code checks for the dir being created. It will make the directory if it doesn't exist.

    :param path: directory path to be created
    :type path: str
    """
    if not os.path.exists(path):
        os.makedirs(path)


class NumberFormat(StrEnum):
    """
    A utility class to make formatting numeric values more expressive.
    """

    SCIENTIFIC = "E"
    FLOATING = "f"

    # TODO: Handle units
    def fmt(self, value: np.float64, precision: int) -> str:
        """
        Format a numeric value as a string to some precision.

        Ideally this method would be called `format`, but we cannot use that because `StrEnum` subclasses `str` and
        `format` is taken.

        :param value: the numeric value to be formatted
        :type value: eleanor.typing.Numeric

        :param precision: the precision to
        """
        if precision < 0:
            raise EleanorException(f"invalid precision {precision} < 0")

        return "{value:.{precision}{fmt}}".format(value=value, precision=precision, fmt=self)


def log_rng(mid: np.floating, error_in_frac: np.floating) -> list[np.floating]:
    """
    Compute the base-10 logarithm of `mid` plus-or-minus some error.

    :param mid: the central value
    :type mid: np.float64

    :param error_in_frac: the +/- fraction
    :type error_in_frac: np.float64

    :return: the base-10 log of `mid +/- error_in_frac * mid`
    :rtype: list[np.float64]
    """
    return [np.log10(mid * _) for _ in [1 - error_in_frac, 1 + error_in_frac]]


def norm_list(data: NDArray[np.floating]) -> list[np.floating]:
    """
    Normalize a list of floating-point values so that the minimum value is 0.0 and the maximum value is 1.0.

    :param data: the list of values
    :type data: `NDArray[np.floating]`

    :return: the normalized list
    :rtype: list[np.float64]
    """
    return list((data - np.min(data)) / (np.max(data) - np.min(data)))


class WorkingDirectory:
    """
    A context manager for changing the current working directory.

    :param path: The path of the new current working directory
    :type path: str
    """

    path: Path
    cwd: Path

    def __init__(self, path: StrPath) -> None:
        self.path = Path(path).resolve()
        self.cwd = Path.cwd()

    def __enter__(self) -> Path:
        """
        Change into the new current working directory that path.

        :return: the absolute path of the new current working directory
        :rtype: str
        """
        os.chdir(self.path)
        self.cwd, self.path = self.path, self.cwd
        return self.cwd

    def __exit__(self, *args: object) -> None:
        """
        Change back to the original current working directory.
        """
        os.chdir(self.path)
        self.cwd, self.path = self.path, self.cwd


def hash_file(path: StrPath, hasher: HashLike | None = None) -> str:
    """
    Hash the contents of a file

    :param path: the path to the filename
    :type path: str | Path

    :param hasher: an (optional) hasher algorithm, defaults to `haslib.sha256`
    :type hasher: haslib._Hash | None

    :return: the hex-encoded hash of the file's contents
    :rtype: str
    """
    if hasher is None:
        hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(4096), b""):
            _ = hasher.update(chunk)
    return hasher.hexdigest()


def hash_dir(path: StrPath, hasher: HashLike | None = None) -> str:
    """
    Compute the hash of a named directory (sha256 by default). The hash is computed in a
    depth-first fashion. For a given directory, this function is called on each subdirectory in
    sorted order. Then :func:`hash_file` is called on each file at that level.

    :param path: path to a directory
    :type path: str | Path

    :param hasher: an (optional) hasher algorithm, defaults to `haslib.sha256`

    :return: the hex-encode sha256 hash of the file contents
    :rtype: str
    """
    if hasher is None:
        hasher = hashlib.sha256()

    contents = [os.path.join(path, f) for f in os.listdir(path)]

    for dir in sorted(filter(os.path.isdir, contents)):
        _ = hash_dir(dir, hasher)

    for filename in sorted(filter(os.path.isfile, contents)):
        _ = hash_file(filename, hasher)

    return hasher.hexdigest()


def convert_to_number(value: int | float | np.floating | str) -> int | np.float64:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, (float, np.floating)):
        return np.float64(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return np.float64(value)
        except ValueError:
            pass
    raise EleanorException("could not convert value to numeric type")


def is_list_of(value: object, types: type | tuple[type, ...], allowNone: bool = False) -> bool:
    if allowNone:
        if isinstance(types, tuple):
            types = (*types, type(None))
        else:
            types = (types, type(None))

    if value is None:
        return allowNone

    if not isinstance(value, list):
        return False
    items = cast(list[object], value)
    return all(isinstance(item, types) for item in items)


def parse_date(date: str) -> datetime.date | datetime.datetime:
    try:
        return datetime.date.fromisoformat(date)
    except ValueError:
        return datetime.datetime.fromisoformat(date)


def chunks(indexable: Sequence[ChunkInputT], n: int) -> Generator[Sequence[ChunkInputT], None, None]:
    N = len(indexable)
    chunk_size = N // n
    residual = N - n * chunk_size
    start = 0
    while residual > 0 and start < N:
        yield indexable[start : start + chunk_size + 1]
        start += chunk_size + 1
        residual -= 1
    while start < N:
        yield indexable[start : start + chunk_size]
        start += chunk_size


def mapreduce(
    mapper: Callable[[MapInputT], ReduceT],
    reducer: Callable[[ReduceT, ReduceT], ReduceT],
    values: Iterable[MapInputT],
    initial: ReduceT,
) -> ReduceT:
    return reduce(reducer, map(mapper, values), initial)


def require_opt_int(value: object, field_name: str) -> int | None:
    """Validate that ``value`` is an int or ``None`` at runtime."""
    if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
        raise EleanorException(f"{field_name} must be an integer")
    return value


def require_int(value: object, field_name: str) -> int:
    """Validate that ``value`` is an int  at runtime."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise EleanorException(f"{field_name} must be an integer")
    return value


def require_opt_str(value: object, field_name: str) -> str | None:
    """Validate that ``value`` is a string or ``None`` at runtime."""
    if value is not None and not isinstance(value, str):
        raise EleanorException(f"{field_name} must be a string")
    return value


def require_str(value: object, field_name: str) -> str:
    """Validate that ``value`` is a string at runtime"""
    if not isinstance(value, str):
        raise EleanorException(f"{field_name} must be a string")
    return value


def require_opt_path(value: object, field_name: str) -> Path | None:
    """Validate that ``value`` is a str, Path or ``None`` at runtime."""
    if isinstance(value, Path):
        return value
    elif isinstance(value, str):
        return Path(value)
    elif value is not None:
        raise EleanorException(f"{field_name} must be a str, Path or None")


def require_path(value: object, field_name: str) -> Path:
    """Validate that ``value`` is a Path at runtime"""
    if isinstance(value, Path):
        return value
    elif isinstance(value, str):
        return Path(value)
    else:
        raise EleanorException(f"{field_name} must be a str or Path")


def require_dict[T](value: object, field_name: str) -> dict[str, T]:
    """Validate that ``value`` is a ``dict`` at runtime and return it typed."""
    if not isinstance(value, dict):
        raise EleanorException(f"{field_name} must be a dictionary")
    return cast(dict[str, T], cast(object, value))


def require_opt_dict[T](value: object, field_name: str) -> dict[str, T] | None:
    """Validate that ``value`` is a ``dict`` or ``None``` at runtime and return it typed."""
    if value is None:
        return value

    if not isinstance(value, dict):
        raise EleanorException(f"{field_name} must be a dictionary")

    return cast(dict[str, T], cast(object, value))


def require_float(value: object, field_name: str) -> np.float64:
    """Validate that ``value`` is a float at runtime"""
    if isinstance(value, float) or (isinstance(value, int) and not isinstance(value, bool)):
        return np.float64(value)
    if isinstance(value, np.floating):
        return cast(np.float64, value)
    raise EleanorException(f"{field_name} must be a floating-point number")


def require_bool(value: object, field_name: str) -> bool:
    """Validate that ``value`` is an boolean at runtime."""
    if not isinstance(value, bool):
        raise EleanorException(f"{field_name} must be a boolean")
    return value


def require_opt_bool(value: object, field_name: str) -> bool | None:
    """Validate that ``value`` is an boolean or None at runtime."""
    if value is not None and not isinstance(value, bool):
        raise EleanorException(f"{field_name} must be a boolean or None")
    return value


def require[T](value: T | None, field_name: str) -> T:
    """Validate that ``value`` is a not ``None`` at runtime"""
    if value is None:
        raise EleanorException(f"{field_name} is required")
    return value


def guard_is_bool(value: object, field_name: str) -> None:
    if not isinstance(value, bool):
        raise EleanorException(f"{field_name} must be a boolean; got {type(value).__name__}")


def guard_is_int(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EleanorException(f"{field_name} must be an int; got {type(value).__name__}")


def guard_is_int_or_none(value: object, field_name: str) -> None:
    if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
        raise EleanorException(f"{field_name} must be an int or None; got {type(value).__name__}")


def guard_is_str(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise EleanorException(f"{field_name} must be a string; got {type(value).__name__}")


def guard_is_str_or_none(value: object, field_name: str) -> None:
    if value is not None and not isinstance(value, str):
        raise EleanorException(f"{field_name} must be an string or None; got {type(value).__name__}")


def guard_is_path(value: object, field_name: str) -> None:
    if not isinstance(value, Path):
        raise EleanorException(f"{field_name} must be a Path; got {type(value).__name__}")


def guard_is_path_or_none(value: object, field_name: str) -> None:
    if value is not None and not isinstance(value, Path):
        raise EleanorException(f"{field_name} must be a Path or None; got {type(value).__name__}")


def guard_is_dict(value: object, field_name: str) -> None:
    if not isinstance(value, dict):
        raise EleanorException(f"{field_name} must be a dictionary")


def guard_is_instance[T](value: object, class_: type[T], field_name: str) -> None:
    if not isinstance(value, class_):
        raise EleanorException(f"{field_name} must be type {class_.__name__}; got {type(value).__name__}")


def guard_is_instance_or_none[T](value: object, class_: type[T], field_name: str) -> None:
    if value is not None and not isinstance(value, class_):
        raise EleanorException(f"{field_name} must be type {class_.__name__} or None; got {type(value).__name__}")
