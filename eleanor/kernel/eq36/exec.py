"""
.. currentmodule:: eleanor.hanger

Provide a simple API for running EQ3/6.
"""

import re
from subprocess import PIPE, Popen, TimeoutExpired

from eleanor.kernel.eq36.codes import RunCode
from eleanor.kernel.eq36.exceptions import Eq36Error
from eleanor.typing import StrPath


def error_guard(output: bytes | str, cmd: str, code: int, fname: str | None = None) -> None:
    """
    Parse EQ3/6 standard output content for error messages and raise an
    :class:`Eq36Error` if any are found.

    :param output: the content of the EQ3/6 output file
    :param cmd: the command that was run
    :param fname: an optional filename to add to the error message
    :raises Eq36Error: if an error message is found
    """
    matches = re.search("Error - (.|\n)*", str(output))
    if matches is not None:
        errors = matches.group(0).split("\\n\\n")
        for error in errors:
            first_message = error.split("\\n\\n")[0]
            trimmed_prefix = first_message.replace("Error - ", str(cmd))
            no_newline = trimmed_prefix.replace("\\n", "")
            message = re.sub("\\s+", " ", no_newline)
            if re.match("^\\s*$", message) is None:
                if fname is None:
                    raise Eq36Error(message, code=code)
                msg = f"{message} in file {fname!r}"
                raise Eq36Error(msg, code=code)


def run(
    cmd: str,
    *args: str,
    timeout: int | None = None,
    code: int,
    fname: str | None = None,
) -> tuple[bytes, bytes]:
    """
    Create and run a subprocess with command :code:`cmd` with arguments
    :code:`args`, capture the standard input and output, and return them.

    :param cmd: the command to run, e.g. `ls`
    :param \\*args: arguments to the command
    :param \\*\\*kwargs: optional keyword arguments to pass to :func:`error_guard`
    :return: the standard output and error
    """
    process = Popen([cmd, *args], stdout=PIPE, stderr=PIPE)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        error_guard(stdout, cmd, code=code, fname=fname)
    except TimeoutExpired as terr:
        process.kill()
        stdout, stderr = process.communicate()
        try:
            error_guard(stdout, cmd, code=code, fname=fname)
        except Eq36Error as e:
            msg = f"{cmd} timed out with errors"
            raise Eq36Error(msg, code=RunCode.EQ36_TIMEOUT) from e
        msg = f"{cmd} timed out without errors"
        raise Eq36Error(msg, code=RunCode.EQ36_TIMEOUT) from terr

    if process.returncode != 0:
        msg = f"{cmd} exited with an unexpected error"
        raise Eq36Error(msg, code=process.returncode)

    return stdout, stderr


def eqpt(data0: str) -> tuple[bytes, bytes]:
    """
    Run eqpt on a data0, writing output files to the current working directory.

    .. Note::
       Calling this function will generate four (or five) files in the current
       working directory: a po, d1, d1f, s and (sometimes) a d0s file. The name
       of the files will depend on the :code:`data0`. For example, if you
       provide :code:`'apples.d1'`, the resulting files will be
       :code:`'apples.po'`, :code:`'apples.d1'`, :code:`'apples.d1f'`,
       :code:`'apples.s'`, and (sometimes) a :code:`'apples.d0s'`

    :param data1: the path to the data1 file
    :param threei: the path to the eq3 input file
    :return: the standard output and error that results from eq3nr on the data1
             and 3i files.
    """
    return run("eqpt", data0, fname=data0, code=RunCode.EQPT_ERROR)


def eq3(data1: StrPath, threei: str, timeout: int | None = None) -> tuple[bytes, bytes]:
    """
    Run eq3nr on a data1 and 3i file, writing output files to the current
    working directory.

    .. Note::
       Calling this function will generate two files in the current working
       directory: a 3o and a 3p file. The name of the file will depend on the
       :code:`threei`. For example, if you provide :code:`'apples.3i'`, the
       resulting files will be :code:`'apples.3o'` and :code:`'apples.3p'`.

    :param data1: the path to the data1 file
    :param threei: the path to the eq3 input file
    :return: the standard output and error that results from eq3nr on the data1
             and 3i files.
    """
    _ = timeout
    return run("eq3nr", str(data1), threei, timeout=None, fname=threei, code=RunCode.EQ3_ERROR)


def eq6(data1: StrPath, sixi: str, timeout: int | None = None) -> tuple[bytes, bytes]:
    """
    Run eq6 on a data1 and 6i file, writing output files to the current working
    directory.

    .. Note::
       Calling this function will generate two files in the current working
       directory: a 6o, 6p, 6ba, 6bb, 6ib, 6t, 6tx, and a 6ts file. The name of
       the file will depend on the :code:`sixi`. For example, if you provide
       :code:`'apples.6i'`, the resulting files will be :code:`'apples.6o'` and
       :code:`'apples.6p'`, :code:`'apples.6ba'`, :code:`'apples.6bb'`,
       :code:`'apples.6ib'`, :code:`'apples.6t'`, :code:`'apples.6tx'`, and a
       :code:`'apples.6ts'`.

    :param data1: the path to the data1 file
    :param sixi: the path to the eq6 input file
    :return: the standard output and error that results from eq6 on the data1
             and 6i files.
    """
    return run("eq6", str(data1), sixi, timeout=timeout, fname=sixi, code=RunCode.EQ6_ERROR)
