import io
import os
import sys
import zipfile
from datetime import datetime
from os.path import join
from tempfile import TemporaryDirectory
from traceback import print_exception

import eleanor.equilibrium_space as es
import eleanor.variable_space as vs

from .exceptions import EleanorException
from .kernel.interface import AbstractKernel
from .output.interface import ComputeResult, ErrorInfo
from .typing import EleanorKwargs, Unpack
from .util import WorkingDirectory


class Sailor(object):
    kernel: AbstractKernel

    def __init__(self, kernel: AbstractKernel):
        self.kernel = kernel

    def dispatch(
        self,
        points: vs.Point | list[vs.Point],
        *args: object,
        **kwargs: Unpack[EleanorKwargs],
    ) -> list[ComputeResult]:
        compute_results: list[ComputeResult] = []

        point_list: list[vs.Point]
        if isinstance(points, list):
            point_list = points
        else:
            point_list = [points]

        for point in point_list:
            vs_point = self.work(point, *args, **kwargs)
            exception: Exception | None = getattr(vs_point, 'exception', None)
            error = None if exception is None else ErrorInfo.from_exception(exception)
            if exception is not None:
                vs_point.exception = None

            compute_results.append(
                ComputeResult(
                    point=vs_point,
                    error=error,
                ))

        return compute_results

    def work(
        self,
        vs_point: vs.Point,
        *args: object,
        **kwargs: Unpack[EleanorKwargs],
    ) -> vs.Point:
        scratch = kwargs.get('scratch', False)
        verbose = kwargs.get('verbose', False)

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
                        code = getattr(e, 'code', None)
                        vs_point.exit_code = code if isinstance(code, int) else -1
                    else:
                        vs_point.exit_code = -1

                vs_point.es_points = es_points
                vs_point.complete_date = datetime.now()

                return vs_point

    @staticmethod
    def collect_scratch(dir: str) -> vs.Scratch | None:
        try:
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_BZIP2, allowZip64=True, compresslevel=9) as zip:
                for filename in os.listdir(dir):
                    zip.write(join(dir, filename), filename)
            return vs.Scratch(id=None, zip=buffer.getvalue())
        except Exception:
            return vs.Scratch(id=None, zip=bytes('\0', 'ascii'))
