import io
import os
import zipfile
from os.path import join
from tempfile import TemporaryDirectory

from .exceptions import EleanorException
from .hanger.tool_room import WorkingDirectory
from .kernel.interface import AbstractKernel
from .models import ESPoint, Scratch, VSPoint
from .typing import Optional
from .yeoman import Yeoman


def collect_scratch(dir: str) -> Optional[Scratch]:
    try:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_BZIP2, allowZip64=True, compresslevel=9) as zip:
            for filename in os.listdir(dir):
                zip.write(join(dir, filename), filename)
        return Scratch(id=None, zip=buffer.getvalue())
    except Exception as e:
        return Scratch(id=None, zip=bytes('\0', 'ascii'))


def sailor(
    kernel: AbstractKernel,
    yeoman: Optional[Yeoman],
    vs_point: VSPoint,
    *args,
    scratch: bool = False,
    **kwargs,
) -> VSPoint:
    with TemporaryDirectory(prefix="eleanor_") as tempdir:
        with WorkingDirectory(tempdir):
            es_points: list[ESPoint] = []
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

            if yeoman is not None:
                yeoman.add(vs_point)

            return vs_point
