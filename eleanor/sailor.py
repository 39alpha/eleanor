import io
import os
import zipfile
from os.path import join
from tempfile import TemporaryDirectory

import ray

import eleanor.equilibrium_space as es
import eleanor.variable_space as vs

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
    yeoman: Optional[Yeoman],
    vs_point: vs.Point,
    *args,
    scratch: bool = False,
    **kwargs,
) -> vs.Point:
    with TemporaryDirectory(prefix="eleanor_") as tempdir:
        with WorkingDirectory(tempdir):
            es_points: list[es.Point] = []
            try:
                es_points = kernel.run(vs_point, *args, **kwargs)
                if scratch:
                    vs_point.scratch = collect_scratch(tempdir)
                exit_code = 0
            except EleanorException as e:
                exit_code = e.code
                vs_point.scratch = collect_scratch(tempdir)
            except Exception as e:
                exit_code = -1
                vs_point.scratch = collect_scratch(tempdir)

            vs_point.es_points = es_points
            vs_point.exit_code = exit_code

            return vs_point


@ray.remote
def sailor(*args, **kwargs) -> vs.Point:
    return __run(*args, **kwargs)
