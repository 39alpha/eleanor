"""
The tool_room contains functions and classes primarily related to
construction of EQ3/6 input files.
"""
import hashlib
import os
import re
import sys
from enum import IntEnum, StrEnum

import numpy as np

from eleanor.exceptions import EleanorException, EleanorFileException, RunCode
from eleanor.typing import Any, NDArray, Number

from .constants import *  # noqa (F403)


# TODO: Use an enumeration for str_loc parameter
def find_files(match: str, location: str = '.', str_loc: str = 'suffix') -> tuple[list[str], list[str]]:
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
    file_names = []
    file_paths = []
    for root, dirs, files in os.walk(location):
        for file in files:
            if str_loc == 'suffix':
                if file.endswith(match):
                    file_names.append(file)
                    file_paths.append(os.path.join(root, file))
            if str_loc == 'prefix':
                if file.startswith(match):
                    file_names.append(file)
                    file_paths.append(os.path.join(root, file))
    return file_names, file_paths


def ensure_directory(path: str) -> None:
    """
    This code checks for the dir being created. It will make the directory if it doesn't exist.

    :param path: directory path to be created
    :type path: str
    """
    if not os.path.exists(path):
        os.makedirs(path)


def mk_check_del_file(path: str) -> None:
    """
    Check if the file being created/moved already exists at the destination.
    """
    if os.path.isfile(path):
        os.remove(path)


def ck_for_empty_file(path: str) -> None:
    """
    Check if path is empty.

    :param path: file path
    :type path: str
    """
    if os.stat(path).st_size == 0:
        print('file: ' + path + ' is empty.')
        sys.exit()


class NumberFormat(StrEnum):
    """
    A utility class to make formatting numeric values more expressive.
    """
    SCIENTIFIC = 'E'
    FLOATING = 'f'

    # TODO: Handle units
    def fmt(self, value: Number, precision: int) -> str:
        """
        Format a numeric value as a string to some precision.

        Ideally this method would be called `format`, but we cannot use that because `StrEnum` subclasses `str` and
        `format` is taken.

        :param value: the numeric value to be formatted
        :type value: eleanor.typing.Numeric

        :param precision: the precision to
        """
        if precision < 0:
            raise EleanorException('invalid precision {precision} < 0')

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


class WorkingDirectory(object):
    """
    A context manager for changing the current working directory.

    :param path: The path of the new current working directory
    :type path: str
    """

    def __init__(self, path: str):
        self.path = os.path.realpath(path)
        self.cwd = os.getcwd()

    def __enter__(self) -> str:
        """
        Change into the new current working directory that path.

        :return: the absolute path of the new current working directory
        :rtype: str
        """
        os.chdir(self.path)
        self.cwd, self.path = self.path, self.cwd
        return self.cwd

    def __exit__(self, *args):
        """
        Change back to the original current working directory.
        """
        os.chdir(self.path)
        self.cwd, self.path = self.path, self.cwd


def hash_file(path: str, hasher=None) -> str:
    """
    Hash the contents of a file

    :param path: the path to the filename
    :type path: str

    :param hasher: an (optional) hasher algorithm, defaults to `haslib.sha256`
    :type hasher: haslib._Hash | None

    :return: the hex-encoded hash of the file's contents
    :rtype: str
    """
    if hasher is None:
        hasher = hashlib.sha256()
    with open(path, 'rb') as handle:
        for bytes in iter(lambda: handle.read(4096), b''):
            hasher.update(bytes)
    return hasher.hexdigest()


def hash_dir(path: str, hasher=None) -> str:
    """
    Compute the hash of a named directory (sha256 by default). The hash is computed in a
    depth-first fashion. For a given directory, this function is called on each subdirectory in
    sorted order. Then :func:`hash_file` is called on each file at that level.

    :param path: path to a directory
    :type path: str

    :param hasher: an (optional) hasher algorithm, defaults to `haslib.sha256`

    :return: the hex-encode sha256 hash of the file contents
    :rtype: str
    """
    if hasher is None:
        hasher = hashlib.sha256()

    contents = list(map(lambda f: os.path.join(path, f), os.listdir(path)))

    for dir in sorted(filter(os.path.isdir, contents)):
        hash_dir(dir, hasher)

    for filename in sorted(filter(os.path.isfile, contents)):
        hash_file(filename, hasher)

    return hasher.hexdigest()
