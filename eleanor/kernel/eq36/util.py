import io
import re
from pathlib import Path

import numpy as np

from eleanor.kernel.eq36.codes import RunCode
from eleanor.kernel.exceptions import EleanorKernelError
from eleanor.typing import StrPath

_FORTRAN_FLOAT_RE: re.Pattern[str] = re.compile(r"([-\+]?\d+(\.\d+)?)([-\+]\d+)")
_NUMERIC_FALLBACK_RE: re.Pattern[str] = re.compile(r"[0-9Ee\+\.-]+")


def get_field(line: str, pos: int) -> str:
    """
    Split the string `line` on spaces and return the `pos`-th
    """
    return line.split()[pos]


def field_as_float(field: str) -> np.float64:
    """
    Parse a string from an EQ3/6 output file as a `float`
    """
    try:
        return np.float64(field)
    except ValueError:
        pass

    match = _FORTRAN_FLOAT_RE.match(field)
    if match:
        return np.float64(match[1] + "e" + match[3])
    fallback = _NUMERIC_FALLBACK_RE.search(field)
    if fallback is not None:
        try:
            return np.float64(fallback[0])
        except ValueError:
            pass

    msg = f"failed to read {field!r} as float"
    raise EleanorKernelError(msg, code=RunCode.PARSER_ERROR)


def read_pickup_lines(file: StrPath | io.TextIOWrapper | None = None) -> list[str]:
    if file is None:
        return read_pickup_lines("problem.3p")

    if isinstance(file, (str, Path)):
        try:
            with Path(file).open("r") as handle:
                return read_pickup_lines(handle)
        except FileNotFoundError as e:
            msg = "failed to open pickup file"
            raise EleanorKernelError(msg, code=RunCode.FILE_ERROR_3P) from e

    try:
        lines = file.readlines()
        for i, line in reversed(list(enumerate(lines))):
            if line.startswith("*---"):
                return lines[i + 1 :]
        msg = "failed to find separator in pickup file"
        raise EleanorKernelError(msg, code=RunCode.FILE_ERROR_3P)
    except FileNotFoundError as e:
        msg = "failed to open pickup file"
        raise EleanorKernelError(msg, code=RunCode.FILE_ERROR_3P) from e
