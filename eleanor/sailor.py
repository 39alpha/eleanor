import io
import os
import zipfile
from os.path import join
from tempfile import TemporaryDirectory

from .exceptions import EleanorException
from .hanger.tool_room import WorkingDirectory
from .kernel.interface import AbstractKernel
from .models import ESPoint, Scratch, VSPoint
from .yeoman import Yeoman


def collect_scratch(dir: str, vs_point: VSPoint):
    try:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_BZIP2, allowZip64=True, compresslevel=9) as zip:
            for filename in os.listdir(dir):
                zip.write(join(dir, filename), filename)

        vs_point.scratch = Scratch(id=None, zip=buffer.getvalue())
    except Exception as e:
        pass


def sailor(kernel: AbstractKernel, yeoman: Yeoman, vs_point: VSPoint, *args, **kwargs) -> None:
    with TemporaryDirectory(prefix="eleanor_") as tempdir:
        with WorkingDirectory(tempdir):
            es_points: list[ESPoint] = []
            try:
                es_points = kernel.run(vs_point, *args, **kwargs)
                exit_code = 0
            except EleanorException as e:
                exit_code = e.code
                collect_scratch(tempdir, vs_point)
            except Exception as e:
                exit_code = -1
                collect_scratch(tempdir, vs_point)

            vs_point.es_points = es_points
            vs_point.exit_code = exit_code
            yeoman.add(vs_point)
