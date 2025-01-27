import io
import os
import sys
import zipfile
from datetime import datetime
from os.path import join
from queue import Queue
from tempfile import TemporaryDirectory
from traceback import print_exception

import eleanor.equilibrium_space as es
import eleanor.variable_space as vs

from .config import DatabaseConfig
from .exceptions import EleanorException
from .kernel.interface import AbstractKernel
from .typing import Optional
from .util import WorkingDirectory
from .yeoman import Yeoman


def collect_scratch(dir: str) -> Optional[vs.Scratch]:
    try:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_BZIP2, allowZip64=True, compresslevel=9) as zip:
            for filename in os.listdir(dir):
                zip.write(join(dir, filename), filename)
        return vs.Scratch(id=None, zip=buffer.getvalue())
    except Exception as e:
        return vs.Scratch(id=None, zip=bytes('\0', 'ascii'))


def __run(
    kernel: AbstractKernel,
    vs_point: vs.Point,
    *args,
    scratch: bool = False,
    verbose: bool = False,
    **kwargs,
) -> vs.Point:
    with TemporaryDirectory(prefix="eleanor_") as tempdir:
        with WorkingDirectory(tempdir):
            vs_point.start_date = datetime.now()
            es_points: list[es.Point] = []
            try:
                es_points = kernel.run(vs_point, *args, **kwargs)
                if scratch:
                    vs_point.scratch = collect_scratch(tempdir)
                exit_code = 0
                vs_point.exception = None
            except EleanorException as e:
                with open('traceback.txt', 'w') as file:
                    print_exception(e, file=file)
                if verbose:
                    print_exception(e, file=sys.stderr)
                exit_code = e.code if e.code is not None else -1
                vs_point.scratch = collect_scratch(tempdir)
                vs_point.exception = e
            except Exception as e:
                with open('traceback.txt', 'w') as file:
                    print_exception(e, file=file)
                if verbose:
                    print_exception(e, file=sys.stderr)
                exit_code = -1
                vs_point.scratch = collect_scratch(tempdir)
                vs_point.exception = e

            vs_point.es_points = es_points
            vs_point.exit_code = exit_code
            vs_point.complete_date = datetime.now()

            return vs_point


def sailor(
    config: DatabaseConfig,
    kernel: AbstractKernel,
    points: vs.Point | list[vs.Point],
    progress: Optional[Queue[bool]],
    *args,
    verbose: bool = False,
    **kwargs,
):
    with Yeoman(config, verbose=verbose) as yeoman:
        if isinstance(points, list):
            for point in points:
                vs_point = __run(kernel, point, *args, verbose=verbose, **kwargs)
                yeoman.write(vs_point)
                if progress is not None:
                    progress.put(True)
        else:
            vs_point = __run(kernel, points, *args, verbose=verbose, **kwargs)
            yeoman.write(vs_point)
            if progress is not None:
                progress.put(True)
