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


class Sailor(object):
    kernel: AbstractKernel
    config: Optional[DatabaseConfig]

    def __init__(self, kernel: AbstractKernel, config: Optional[DatabaseConfig] = None):
        self.kernel = kernel
        self.config = config

    def dispatch(
        self,
        points: vs.Point | list[vs.Point],
        *args,
        progress: Optional[Queue[bool]] = None,
        verbose: bool = False,
        success_sampling: bool = False,
        **kwargs,
    ) -> list[int]:
        if self.config is None:
            raise EleanorException('cannot dispatch sailor without a config', code=-1)

        vs_point_ids: list[int] = []
        with Yeoman(self.config, verbose=verbose) as yeoman:
            if isinstance(points, list):
                for point in points:
                    vs_point = self.work(point, *args, verbose=verbose, **kwargs)
                    show_progress = not success_sampling or vs_point.exit_code == 0
                    yeoman.write(vs_point, refresh=True)
                    if vs_point.id is None:
                        raise EleanorException("variable space point does not have an id after insert")
                    vs_point_ids.append(vs_point.id)
                    if progress is not None and show_progress:
                        progress.put(True)
            else:
                vs_point = self.work(points, *args, verbose=verbose, **kwargs)
                show_progress = not success_sampling or vs_point.exit_code == 0
                yeoman.write(vs_point, refresh=True)
                if vs_point.id is None:
                    raise EleanorException("variable space point does not have an id after insert")
                vs_point_ids.append(vs_point.id)
                if progress is not None and show_progress:
                    progress.put(True)
        return vs_point_ids

    def work(
        self,
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
                    es_points = self.kernel.run(vs_point, *args, **kwargs)
                    if scratch:
                        self.kernel.copy_data(vs_point)
                        vs_point.scratch = Sailor.collect_scratch(tempdir)
                    vs_point.exit_code = 0
                except Exception as e:
                    self.kernel.copy_data(vs_point)
                    with open('traceback.txt', 'w') as file:
                        print_exception(e, file=file)
                    if verbose:
                        print_exception(e, file=sys.stderr)
                    vs_point.scratch = Sailor.collect_scratch(tempdir)
                    vs_point.exception = e
                    if isinstance(e, EleanorException):
                        vs_point.exit_code = e.code if e.code is not None else -1
                    else:
                        vs_point.exit_code - 1

                vs_point.es_points = es_points
                vs_point.complete_date = datetime.now()

                return vs_point

    @staticmethod
    def collect_scratch(dir: str) -> Optional[vs.Scratch]:
        try:
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_BZIP2, allowZip64=True, compresslevel=9) as zip:
                for filename in os.listdir(dir):
                    zip.write(join(dir, filename), filename)
            return vs.Scratch(id=None, zip=buffer.getvalue())
        except Exception as e:
            return vs.Scratch(id=None, zip=bytes('\0', 'ascii'))
